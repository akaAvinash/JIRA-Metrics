#!/usr/bin/env python3

import json
import os
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
from lasso_auth import LassoTokenClient

# Suppressing FutureWarnings
import warnings
warnings.filterwarnings("ignore", category=FutureWarning, message="Setting an item of incompatible dtype is deprecated")

# Jira credentials
Jira_ID = 'API_Usernam'
Jira_Passsword = 'API_Pwd'

class JiraReportGenerator:
    def __init__(self, api_url, json_file_path, jira_id, jira_password):
        self.api_url = api_url
        self.json_file_path = json_file_path
        self.auth = self.get_lasso_auth(jira_id, jira_password)

    def get_lasso_auth(self, jira_id, jira_password):
        lasso_token_client = LassoTokenClient("https://api.lasso.labcollab.net/rest/user/token", jira_id, jira_password, "LabCollabJira")
        access_token = lasso_token_client.get_access_token()
        return ('lasso', access_token)

    def calculate_overall_metrics(self, report_layout):
        priorities = ['Blocker', 'Critical', 'Others']
        overall_resolved, overall_bugs_raised, overall_noise_issues, overall_fixed_issues, overall_gerrit_issues = 0, 0, 0, 0, 0

        for priority in priorities:
            overall_resolved += report_layout.loc['Resolved', ('Regression', priority)] + report_layout.loc['Resolved', ('Exploratory', priority)]
            overall_bugs_raised += report_layout.loc['BugsRaised', ('Regression', priority)] + report_layout.loc['BugsRaised', ('Exploratory', priority)]
            overall_noise_issues += report_layout.loc['Noise', ('Regression', priority)] + report_layout.loc['Noise', ('Exploratory', priority)]
            overall_fixed_issues += report_layout.loc['Fixed', ('Regression', priority)] + report_layout.loc['Fixed', ('Exploratory', priority)]
            overall_gerrit_issues += report_layout.loc['GerritFix', ('Regression', priority)] + report_layout.loc['GerritFix', ('Exploratory', priority)]

        overall_noise_percentage = (overall_noise_issues / overall_resolved) * 100
        overall_fixed_percentage = (overall_fixed_issues / overall_resolved) * 100
        overall_gerrit_percentage = (overall_gerrit_issues / overall_resolved) * 100
        overall_resolution_percentage = (overall_resolved / overall_bugs_raised) * 100

        for priority in priorities:
            report_layout.loc["Noise%", ('Overall')] = f"{overall_noise_percentage:.2f}%"
            report_layout.loc["Fixed%", ('Overall')] = f"{overall_fixed_percentage:.2f}%"
            report_layout.loc["Gerrit%", ('Overall')] = f"{overall_gerrit_percentage:.2f}%"
            report_layout.loc["Resolution%", ('Overall')] = f"{overall_resolution_percentage:.2f}%"

    def fetch_and_sort_data(self, jql_query):
        try:
            logging.info("Fetching data for JQL query: %s", jql_query)
            response = requests.get(
                self.api_url,
                headers={'Authorization': f'Bearer {self.auth[1]}'},
                params={'jql': jql_query, 'startAt': 0, 'maxResults': 10000}
            )
            response.raise_for_status()
            response_data = response.json()
            logging.info("Successfully fetched data for JQL query: %s", jql_query)
            return response_data.get('issues', [])
        except requests.exceptions.RequestException as err:
            logging.error("Jira API request failed for JQL query %s: %s", jql_query, err)
            return []

    def fetch_resolution_data(self, jql_query):
        try:
            response = requests.get(
                self.api_url,
                headers={'Authorization': f'Bearer {self.auth[1]}'},
                params={'jql': jql_query}
            )
            response.raise_for_status()
            return response.json().get('issues', [])
        except requests.exceptions.RequestException as e:
            logging.error("Jira API request failed for Resolution data: %s", str(e))
            return []

    def create_report_layout(self):
        columns = pd.MultiIndex.from_tuples([
            ('Regression', 'Blocker'), ('Regression', 'Critical'), ('Regression', 'Others'),
            ('Exploratory', 'Blocker'), ('Exploratory', 'Critical'), ('Exploratory', 'Others'),
            ('Overall', '')],
            names=['Metrics', 'Priority'])
        index = ['BugsRaised', 'Resolved', 'Noise', 'GerritFix', 'Fixed', 'Noise%', 'Fixed%', 'Gerrit%', 'Resolution%']
        data = [[0] * len(columns) for _ in range(len(index))]
        df = pd.DataFrame(data, columns=columns, index=index)
        return df

    def validate_report_data(self, report_layout, data, common_sub_queries, start_date, end_date):
        success = True

        for sub_query in common_sub_queries:
            regression_sub_query = data["Regression"].get(sub_query)
            exploratory_sub_query = data["Exploratory"].get(sub_query)

            if regression_sub_query is None or exploratory_sub_query is None:
                logging.error("JQL query for '%s' not found in JSON data.", sub_query)
                success = False

        return success

    def calculate_metrics(self, report_layout):
        priorities = ['Blocker', 'Critical', 'Others']

        for priority in priorities:
            noise_issues = report_layout.loc['Noise', ('Regression', priority)]
            resolved_issues = report_layout.loc['Resolved', ('Regression', priority)]

            if resolved_issues != 0:
                noise_percentage = (noise_issues / resolved_issues) * 100
                report_layout.loc["Noise%", ('Regression', priority)] = f"{noise_percentage:.2f}%"
            else:
                report_layout.loc["Noise%", ('Regression', priority)] = '0.0%'

            fixed_issues = report_layout.loc['Fixed', ('Regression', priority)]
            resolved_issues = report_layout.loc['Resolved', ('Regression', priority)]
            gerrit_issues = report_layout.loc['GerritFix', ('Regression', priority)]

            if resolved_issues != 0:
                fixed_percentage = (fixed_issues / resolved_issues) * 100
                gerrit_percentage = (gerrit_issues / resolved_issues) * 100

                report_layout.loc["Fixed%", ('Regression', priority)] = f"{fixed_percentage:.2f}%"
                report_layout.loc["Gerrit%", ('Regression', priority)] = f"{gerrit_percentage:.2f}%"
            else:
                report_layout.loc["Fixed%", ('Regression', priority)] = '0.0%'
                report_layout.loc["Gerrit%", ('Regression', priority)] = '0.0%'

            bugs_raised = report_layout.loc['BugsRaised', ('Regression', priority)]
            resolved_issues = report_layout.loc['Resolved', ('Regression', priority)]

            if bugs_raised > 0:
                resolution_percentage = (resolved_issues / bugs_raised) * 100
            else:
                resolution_percentage = 0

            report_layout.loc["Resolution%", ('Regression', priority)] = f"{resolution_percentage:.2f}%"

        for priority in priorities:
            noise_issues = report_layout.loc['Noise', ('Exploratory', priority)]
            resolved_issues = report_layout.loc['Resolved', ('Exploratory', priority)]

            if resolved_issues != 0:
                noise_percentage = (noise_issues / resolved_issues) * 100
                report_layout.loc["Noise%", ('Exploratory', priority)] = f"{noise_percentage:.2f}%"
            else:
                report_layout.loc["Noise%", ('Exploratory', priority)] = '0.0%'

            fixed_issues = report_layout.loc['Fixed', ('Exploratory', priority)]
            resolved_issues = report_layout.loc['Resolved', ('Exploratory', priority)]
            gerrit_issues = report_layout.loc['GerritFix', ('Exploratory', priority)]

            if resolved_issues != 0:
                fixed_percentage = (fixed_issues / resolved_issues) * 100
                gerrit_percentage = (gerrit_issues / resolved_issues) * 100

                report_layout.loc["Fixed%", ('Exploratory', priority)] = f"{fixed_percentage:.2f}%"
                report_layout.loc["Gerrit%", ('Exploratory', priority)] = f"{gerrit_percentage:.2f}%"
            else:
                report_layout.loc["Fixed%", ('Exploratory', priority)] = '0.0%'
                report_layout.loc["Gerrit%", ('Exploratory', priority)] = '0.0%'

            bugs_raised = report_layout.loc['BugsRaised', ('Exploratory', priority)]
            resolved_issues = report_layout.loc['Resolved', ('Exploratory', priority)]

            if bugs_raised > 0:
                resolution_percentage = (resolved_issues / bugs_raised) * 100
            else:
                resolution_percentage = 0

            report_layout.loc["Resolution%", ('Exploratory', priority)] = f"{resolution_percentage:.2f}%"

    def generate_monthly_reports(self, start_date, end_date):
        start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
        end_datetime = datetime.strptime(end_date, "%Y-%m-%d")

        while start_datetime <= end_datetime:
            current_month_start = start_datetime.strftime("%Y-%m-01")
            current_month_end = (start_datetime + timedelta(days=31)).replace(day=1) - timedelta(days=1)
            current_month_end = current_month_end.strftime("%Y-%m-%d")

            month_name = start_datetime.strftime("%B")
            report_filename = f"report_{month_name}_{start_datetime.year}.xlsx"

            self.generate_report(current_month_start, current_month_end, report_filename)
            start_datetime = (start_datetime + timedelta(days=32)).replace(day=1)

    def generate_report(self, start_date, end_date, report_filename):
        try:
            with open(self.json_file_path, 'r') as json_file:
                data = json.load(json_file)
        except FileNotFoundError as e:
            logging.error("JSON file not found: %s", str(e))
            return

        api_credentials = data["api_credentials"]
        api_username = api_credentials["api_username"]
        api_password = api_credentials["api_password"]
        api_url = api_credentials["api_url"]

        common_sub_queries = ["BugsRaised", "Resolved", "Fixed", "GerritFix", "Noise", "Resolution"]

        jql_queries_data = {"Regression": {}, "Exploratory": {}}
        jql_queries_df = pd.DataFrame(jql_queries_data)
        report_layout = self.create_report_layout()

        if self.validate_report_data(report_layout, data, common_sub_queries, start_date, end_date):
            for sub_query in common_sub_queries:
                regression_sub_query = data["Regression"][sub_query].replace("{{start_date}}", start_date).replace("{{end_date}}", end_date)
                exploratory_sub_query = data["Exploratory"][sub_query].replace("{{start_date}}", start_date).replace("{{end_date}}", end_date)

                regression_data = self.fetch_and_sort_data(regression_sub_query)
                exploratory_data = self.fetch_and_sort_data(exploratory_sub_query)

                for priority in ['Blocker', 'Critical', 'Others']:
                    if priority == 'Others':
                        priority_issues = [issue for issue in regression_data if issue['fields']['priority']['name'] not in ['Blocker', 'Critical']]
                    else:
                        priority_issues = [issue for issue in regression_data if issue['fields']['priority']['name'] == priority]
                    report_layout.loc[sub_query, ('Regression', priority)] = len(priority_issues)

                    if priority == 'Others':
                        priority_issues = [issue for issue in exploratory_data if issue['fields']['priority']['name'] not in ['Blocker', 'Critical']]
                    else:
                        priority_issues = [issue for issue in exploratory_data if issue['fields']['priority']['name'] == priority]
                    report_layout.loc[sub_query, ('Exploratory', priority)] = len(priority_issues)

                overall_regression = sum(report_layout.loc[sub_query, ('Regression', priority)] for priority in ['Blocker', 'Critical', 'Others'])
                overall_exploratory = sum(report_layout.loc[sub_query, ('Exploratory', priority)] for priority in ['Blocker', 'Critical', 'Others'])
                report_layout.loc[sub_query, ('Overall', '')] = overall_regression + overall_exploratory

                resolution_sub_query = data["Regression"]["Resolution"].replace("{{start_date}}", start_date).replace("{{end_date}}", end_date)
                resolution_data = self.fetch_and_sort_data(resolution_sub_query)

                for priority in ['Blocker', 'Critical', 'Others']:
                    bugs_raised = report_layout.loc['BugsRaised', ('Regression', priority)]
                    resolution_count = len(resolution_data)
                    resolution_percentage = (resolution_count / bugs_raised) * 100

                    report_layout.loc["Resolution%", ('Regression', priority)] = resolution_percentage

                    jql_queries_df.loc[sub_query, ('Regression')] = regression_sub_query
                    jql_queries_df.loc[sub_query, ('Exploratory')] = exploratory_sub_query
            
            report_layout = report_layout.drop("Resolution", errors='ignore')
            self.calculate_metrics(report_layout)
            self.calculate_overall_metrics(report_layout)

            report_layout = report_layout.applymap(lambda x: str(x).rstrip("days"))
            report_layout = report_layout.fillna('')

            print(report_layout)
            
            report_directory = "reports"

            if not os.path.exists(report_directory):
                os.makedirs(report_directory)

            report_filepath = os.path.join(report_directory, report_filename)

            report_layout.to_excel(report_filepath, index=True)
            print(f"Report saved to {report_filepath}")
        else:
            logging.error("Validation failed. Please check the errors in the log.")

    def combine_reports(self):
        report_directory = "reports"
        report_files = os.listdir(report_directory)
        report_files = [file for file in report_files if file.endswith('.xlsx')]
        combined_data = pd.DataFrame()

        for report_file in report_files:
            report_filepath = os.path.join(report_directory, report_file)
            report_data = pd.read_excel(report_filepath, index_col=0)
            combined_data = pd.concat([combined_data, report_data], axis=0)

        combined_report_filename = "combined_report.xlsx"
        combined_report_filepath = os.path.join(report_directory, combined_report_filename)
        combined_data.to_excel(combined_report_filepath)
        print(f"Combined report saved to {combined_report_filepath}")

def main():
    logging.basicConfig(level=logging.ERROR)

    if not os.path.exists("reports"):
        os.makedirs("reports")

    base_directory = "/path/Report_Script/QMR_json/"
    json_options = {"Option1": "Option1.json", "Option2": "Option2.json"}

    while True:
        print("Choose an option:")
        for option in json_options:
            print(f"{option}: {json_options[option]}")

        user_choice = input("Enter your choice: ")

        if user_choice in json_options:
            selected_json_file = json_options[user_choice]
            json_file_path = os.path.join(base_directory, selected_json_file)

            break
        else:
            print("Invalid choice. Please choose a valid option.")

    try:
        with open(json_file_path, 'r') as json_file:
            data = json.load(json_file)
    except FileNotFoundError as e:
        logging.error("JSON file not found: %s", str(e))
        return
    except KeyError:
        logging.error("API credentials not found in JSON data.")
        return

    api_credentials = data.get("api_credentials")
    if api_credentials is None:
        logging.error("API credentials not found in JSON data.")
        return

    api_username = api_credentials.get("api_username")
    api_password = api_credentials.get("api_password")
    api_url = api_credentials.get("api_url")

    if not api_username or not api_password or not api_url:
        logging.error("API credentials incomplete in JSON data.")
        return

    auth = (api_username, api_password)

    jira_report_generator = JiraReportGenerator(api_url, json_file_path, Jira_ID, Jira_Passsword)
    start_date = input("Enter start date (YYYY-MM-DD): ")
    end_date = input("Enter end date (YYYY-MM-DD): ")

    jira_report_generator.generate_monthly_reports(start_date, end_date)
    jira_report_generator.combine_reports()

if __name__ == "__main__":
    main()
