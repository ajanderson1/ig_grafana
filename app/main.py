import json
from configparser import ConfigParser
import os
import time
import sys
import getopt
import yfinance as yf
from influxdb import InfluxDBClient
import pprint as pp
import logging
from requests import request, get
import requests
import pandas as pd
import numpy
import pprint as pp

logging.basicConfig(level=logging.INFO)
log = logging.getLogger()
log.info("INFO log displaying")  # log test


class SuiviBourse:
    def __init__(self, argv):
        try:
            opts, _ = getopt.getopt(
                argv, "hH:p:D:U:P:i:c:", [
                    "help", "host=", "port=", "database=", "username=",
                    "password=", "interval=", "config="]
            )
        except getopt.GetoptError as err:
            print(err)
            usage()
            sys.exit(2)

        influxHost = os.getenv('INFLUXDB_HOST', default='localhost')
        influxPort = os.getenv('INFLUXDB_PORT', default=8086)
        influxDatabase = os.getenv('INFLUXDB_DATABASE', default='bourse')
        influxUsername = ""
        influxPassword = ""

        self.appScrapingInterval = int(
            os.getenv('APP_SCRAPING_INTERVAL', default=60))
        self.configFilePath = os.getenv(
            'APP_FILE_PATH', default='/home/pi/GitHub/suivi-bourse-app/config.conf')

        for opt, arg in opts:
            if opt in ("-h", "--help"):
                usage()
                sys.exit(0)
            elif opt in ("-H", "--host"):
                influxHost = arg
            elif opt in ("-p", "--port"):
                influxPort = arg
            elif opt in ("-D", "--database"):
                influxDatabase = arg
            elif opt in ("-U", "--username"):
                influxUsername = arg
            elif opt in ("-P", "--password"):
                influxPassword = arg
            elif opt in ("-i", "--interval"):
                self.appScrapingInterval = int(arg)
            elif opt in ("-c", "--config"):
                self.configFilePath = arg

        self.influxdbClient = InfluxDBClient(
            host=influxHost, port=influxPort, database=influxDatabase,
            username=influxUsername, password=influxPassword)

        if os.path.isfile(self.configFilePath):
            self.config = ConfigParser()
            self.config.read(self.configFilePath)
            print(self.config.sections())
        else:
            print("Config file not found")

        self.IG_X_API_KEY = self.config["Auth"]["IG_X_API_KEY"]
        self.IG_X_SECURITY_TOKEN = self.config["Auth"]["IG_X_SECURITY_TOKEN"]
        self.IG_CST = self.config["Auth"]["IG_CST"]

        print('This is the API KEY!:', self.IG_X_API_KEY)

    def check(self):
        self.influxdbClient.ping()
        if(not os.path.exists(self.configFilePath)):
            raise Exception(
                "File {} doesn't exist !".format(self.configFilePath))

    def run(self):
        pass
        # with open(self.appDataFilePath) as data_file:
        #    data = json.load(data_file)
        # share is taking each item in the json - so in my case each item is 'account' which is already the info i need there.
        # dont need the complex data exprapolation below     //     last_quote = (history.tail(1)['Close'].iloc[0])
        self.influxdbClient.write_points(self.get_account_info(
            IG_X_API_KEY=self.IG_X_API_KEY, IG_X_SECURITY_TOKEN=self.IG_X_SECURITY_TOKEN, IG_CST=self.IG_CST))
        self.influxdbClient.close()

    def get_account_info(self, IG_X_API_KEY=None, IG_X_SECURITY_TOKEN=None, IG_CST=None, account_info_url="https://demo-api.ig.com/gateway/deal/accounts", HEADER_CONTENT_TYPE="application/json; charset=UTF-8", HEADER_CONTENT_ACCEPT="application/json; charset=UTF-8", IG_VERSION="1"):
        account_headers = {
            'Content-Type': HEADER_CONTENT_TYPE,
            'Accept': HEADER_CONTENT_ACCEPT,
            'X-IG-API-KEY': IG_X_API_KEY,
            'version': IG_VERSION,
            'X-SECURITY-TOKEN': IG_X_SECURITY_TOKEN,
            'CST': IG_CST
        }

        r = requests.get(account_info_url, headers=account_headers)
        d = r.json()  # makes request into JSON (dict)
        # to prove oringal JSON is correct and nicely formatted
        print('original JSON below:\n', json.dumps(
            d, indent=4, sort_keys=True))

        # flattens the JSON (dict): d (dataframe) - now too flat??? not two separate things hmmmmm
        d_normalised = pd.json_normalize(d['accounts'])
        # makes into a JSON (dict) ready to use
        d_normalised_dict = d_normalised.to_dict('records')

        #  d_normalised_json = d_normalised.to_json(orient='records')[1:-1].replace('},{', '} {')   # this line put all the escape chars in but i think would still work (using to_dict instead)

        whichAccount = 'Demo-SpreadBet'
        # margin = d_normalised.loc[snapshot['accountName'] == whichAccount]['balance.deposit']
        # profit_loss = d_normalised.iloc[0]['balance.profitLoss']
        # balance = d_normalised.iloc[0]['balance.balance']

        # preparing just the account im interested in (whichAcccout) ready to prepare in influxDB JSON
        single_account_info = d_normalised.loc[d_normalised['accountName']
                                               == whichAccount]
        single_account_info_dict = single_account_info.to_dict(
            'records')  # makes into a JSON (dict) ready to use
        single_account_info_json = single_account_info.to_json(
            orient='records')[1:-1].replace('},{', '} {')

        final_data = single_account_info_dict
        # to show the new format ready to iterate through
        print('new JSON below:\n', json.dumps(
            final_data, indent=4, sort_keys=True))

        for share in final_data:
            json_body = [
                {
                    "measurement": "account_information",
                    "tags": {
                        "accountAlias": "",  # share['accountAlias'],
                        "accountId": share['accountId'],
                        "accountName": share['accountName'],
                        "accountType": share['accountType'],
                        "canTransferFrom": share['canTransferFrom'],
                        "canTransferTo": share['canTransferTo'],
                        "currency": share['currency'],
                        "preferred": share['preferred'],
                        "status": share['status']
                    },
                    "fields": {
                        "balance_available": share['balance.available'],
                        "balance_balance": share['balance.balance'],
                        "balance_deposit": share['balance.deposit'],
                        "balance_profitLoss": share['balance.profitLoss']
                    }
                }
            ]
        return json_body


def usage():
    print("\nUsage: python3 main.py [OPTIONS]")
    print("\nOPTION\t\t\tDESCRIPTION")
    print("-h, --help\t\tShow manual")
    print("-H, --host\t\tInfluxDB Host")
    print("-p, --port\t\tInfluxDB Port")
    print("-D, --database\t\tInfluxDB Database")
    print("-U, --username\t\tInfluxDB Username")
    print("-P, --password\t\tInfluxDB Password")
    print("-i, --interval\t\tApplication Scraping Interval (seconds)")
    print("-c, --config\t\tData file path")


if __name__ == "__main__":
    error_counter = 0
    suivi = SuiviBourse(sys.argv[1:])
    # while True:  # commen this to hjust run once!
    try:
        suivi.check()
        suivi.run()
        error_counter = 0
    except Exception as err:
        print("An error has occured: " + str(err))
        error_counter += 1
        if error_counter >= 5:
            print("5 consecutive errors : Exiting the app")
            sys.exit(1)
    finally:
        time.sleep(suivi.appScrapingInterval)
