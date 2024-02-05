# Simple Inflation Indexer

This is a python script that uses (urban) cpi data to show how much inflation has deprecated the value of money over time.

This is done over a monthly resolution. run the script with python.

## requirements

python packages:

- requests
- BeautifulSoup
- PyPDF2
- pandas
- numpy

os packages:

- cURL

## usage

```
usage: calc_inflation.py [-h] [-e END] [-s START] [-m MONEY] [-i INDEX_MONTH] [-l {us,pk}]`

options:
  -h, --help            show this help message and exit
  -e END, --end END     end month of whole time range in YYYY-MM format, current month by default
  -s START, --start START
                        start month of whole time range in YYYY-MM format, a year before end by default
  -m MONEY, --money MONEY
                        the monetary amount to index by inflation
  -i INDEX_MONTH, --index-month INDEX_MONTH
                        month to index inflation values by, this month's value will be the same as entered in --index-amount
  -l {us,pk}, --locale {us,pk}
                        the country for which inflation will be indexed
```