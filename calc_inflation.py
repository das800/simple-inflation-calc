import requests
from bs4 import BeautifulSoup
from io import BytesIO
import PyPDF2
import datetime
import pandas as pd
import numpy as np
import os
import argparse
import subprocess
import json
import shlex


def valid_date(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m").date().replace(day=1)
    except ValueError:
        msg = f"Not a valid date: '{s}'. Expected format: YYYY-MM"
        raise argparse.ArgumentTypeError(msg)

parser = argparse.ArgumentParser()
parser.add_argument('-e', '--end', help='end month of whole time range in YYYY-MM format, current month by default', type=valid_date, default=datetime.datetime.now().strftime("%Y-%m"))
parser.add_argument('-s', '--start', help='start month of whole time range in YYYY-MM format, a year before end by default', type=valid_date, default=None)
parser.add_argument('-m', '--money', help='the monetary amount to index by inflation', type=float, default=None)
parser.add_argument('-i', '--index-month', help='month to index inflation values by, this month\'s value will be the same as entered in --index-amount', type=valid_date, default=None)
parser.add_argument('-l', '--locale', choices=['us', 'pk'], help='the country for which inflation will be indexed', default='us')

args = parser.parse_args()

if not args.start:
	args.start = (args.end - datetime.timedelta(days=365)).replace(day=1) #this probably works for leap years. probably

assert args.end >= args.start, f"end month ({args.end}) must be later than start month ({args.start})"
assert (args.money and args.index_month) or (not args.money and not args.index_month), 'must have either both --money and --index-month or neither'
if args.index_month:
	assert args.end >= args.index_month >= args.start, f'index month ({args.index_month}) must be within requested range ({args.start}, {args.end})'


def get_us_cpi(start_month, end_month):
	'''
	this gets the series CWSR0000SA0, which is described as "All items in U.S. city average, urban wage earners and clerical workers, seasonally adjusted" (https://download.bls.gov/pub/time.series/cw/cw.series)
	'''

	command = shlex.split(f'''
	curl -s -X POST -H 'Content-Type: application/json' 
     -d '{{"seriesid":["CWSR0000SA0"],
        "startyear":"{start_month.year}", "endyear":"{end_month.year}"}}' 
        https://api.bls.gov/publicAPI/v2/timeseries/data/
	''')

	process = subprocess.Popen(command, stdout=subprocess.PIPE)
	(output, error) = process.communicate()

	response_js = json.loads(output.decode())

	cpi_data = []
	for month_data in response_js['Results']['series'][0]['data']: #only 1 series was requested above (CWSR0000SA0)
		month = datetime.datetime(int(month_data['year']), int(month_data['period'].strip('M')), 1).date()

		if not (end_month >= month >= start_month):
			continue
		print(f"processing {month}")

		ucpi = float(month_data['value'])

		cpi_data.append([month, ucpi])

	cpi_df = pd.DataFrame(cpi_data, columns = ['monthstamp', 'urban_cpi']).set_index('monthstamp')
	return cpi_df


def get_pk_cpi(start_month, end_month):
	'''
	the cpi webpage lists links to each months report, a pdf file from which the cpi must be read
	'''

	base_url = 'https://www.pbs.gov.pk/'

	is_start_date_reached = False #need to traverse through months on each page until the start month is reached, no way to go to start month directly

	page = 0
	cpi_data = []
	while not is_start_date_reached:
		html = requests.get(f"{base_url}cpi?page={page}").text

		soup = BeautifulSoup(html, 'html.parser')
		rows = soup.find_all('div', {'class': 'view-content row'})[0].find_all('div', {'class': 'views-row'}) #very brittle, will need to update when webpage changes

		for row in rows:
			month = datetime.datetime.strptime(row.find('h5').text.strip().replace(',', ''), '%B %Y').date().replace(day=1) #brittle, update with webpage
			if month < start_month:
				is_start_date_reached = True
				continue
			
			if month > end_month:
				continue

			print(f"processing {month}")

			res_pdf = requests.get(f"{base_url}{row.find('a')['href']}") #brittle, update with webpage

			raw_pdf = res_pdf.content

			with BytesIO(raw_pdf) as pdf_data:
				report = PyPDF2.PdfReader(pdf_data)
				for page_num in range(len(report.pages)):
					page_text = report.pages[page_num].extract_text()

					#entire rest of this for loop is brittle, will need to update with pdf format changes
					page_lines = page_text.split('\n')
					if len(page_lines) < 3:
						continue
					if 'II.UrbanConsumerPriceIndex(UCPI)' in ''.join(page_lines[:3]).replace('\n', '').replace(' ', ''):
						for line in page_lines:
							if line[:18] == ' General  100.00  ':	
								ucpi = float(line.split('  ')[2].split(' ')[0])
								break
						break
			cpi_data.append([month, ucpi])
		page += 1

	cpi_df = pd.DataFrame(cpi_data, columns = ['monthstamp', 'urban_cpi']).set_index('monthstamp')
	return cpi_df

def main():

	locale_cpi_processors = {
		'us': get_us_cpi,
		'pk': get_pk_cpi
	}

	cpi_df = locale_cpi_processors[args.locale](args.start, args.end)

	#sanity check, are values contiguous?
	time_steps = [-td / np.timedelta64(1, 'D') for td in cpi_df.index.to_series().diff().dropna().unique()]
	assert all([td in {28, 30, 31}for td in time_steps]), "rows are not adjacent months for some reason ???"

	cpi_df['month'] = cpi_df.index.to_series().apply(lambda monthstamp: monthstamp.strftime('%B'))
	cpi_df['year'] = cpi_df.index.to_series().apply(lambda monthstamp: monthstamp.strftime('%Y'))
	cpi_df = cpi_df.sort_index(ascending=True)
	cpi_df = cpi_df[['month', 'year', 'urban_cpi']]

	if args.money and args.index_month:
		index_val = cpi_df.loc[args.index_month, 'urban_cpi']
		index_colname = f"index_{args.index_month.strftime('%Y-%m')}"
		cpi_df[index_colname] = (cpi_df['urban_cpi'] / index_val)
		cpi_df['indexed_monetary_value'] = cpi_df[index_colname] * args.money

	print(cpi_df)
	monthstamp_ls = cpi_df.index.to_list()
	output_filename = f"{monthstamp_ls[0].strftime('%Y%m')}_{monthstamp_ls[-1].strftime('%Y%m')}_ucpi.csv"
	cpi_df.to_csv(output_filename, index = False)

main()
