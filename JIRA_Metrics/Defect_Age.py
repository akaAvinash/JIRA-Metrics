#!/usr/bin/env python3


import requests
from datetime import datetime, timedelta
import pandas as pd
import json
from lasso_auth import LassoTokenClient
from urllib.parse import quote
import warnings
import os

warnings.simplefilter(action='ignore', category=FutureWarning)


def lasso_authenticate():
    """
    Authenticate using LassoTokenClient and return Jira options.

    :return: Jira options dictionary
    """
    try:
        lasso_client = LassoTokenClient(
            lasso_token_url='https://api.lasso.instance.net/rest/user/token',
            username='username',
            password='pwd',
            service='name'
        )

        jira_options = {'server': 'https://issues.labcollab.net', 'verify': True}
        jira_access_token = lasso_client.get_access_token()
        headers = {'Authorization': f'Bearer {jira_access_token}'}
        jira_options['headers'] = headers

        return jira_options
    except Exception as e:
        print(f"Lasso authentication failed: {e}")
        return {}  

jira_options = lasso_authenticate()


# Specify the common path to the JSON files
json_files_path = "/path/Report_Script/defect_age_json/"

# Create a dictionary to map user input to JSON file names
json_files = {
    "Option1": "Option1.json",
    "Option2": "Option2.json",
}

# Prompt the user for their choice of section
while True:
    section_choice = input("Enter the section (Option1, Option2): ").strip()
    if section_choice in json_files:
        json_file_name = json_files[section_choice]
        json_file_path = f"{json_files_path}{json_file_name}"
        break
    print("Invalid section choice. Please choose from Option1 , Option2.")

# Load the selected JSON file
with open(json_file_path, "r") as json_file:
    queries = json.load(json_file)


# Prompt the user for start and end dates
start_date = input("Enter the start date (YYYY-MM-DD): ")
end_date = input("Enter the end date (YYYY-MM-DD): ")

# Update the JQL queries in memory with the user-provided date range
for key in queries:
    queries[key] = [query.replace("{{start_date}}", start_date).replace("{{end_date}}", end_date)
                    for query in queries[key]]
    
# Convert input dates to datetime objects
start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
end_datetime = datetime.strptime(end_date, "%Y-%m-%d")

# Use queries as needed in your script
regression_resolved_queries = queries["regression_resolved_queries"]
regression_unresolved_queries = queries["regression_unresolved_queries"]
exploratory_resolved_queries = queries["exploratory_resolved_queries"]
exploratory_unresolved_queries = queries["exploratory_unresolved_queries"]


def calculate_average_age(jql_query, resolved=True):
    """
    Calculate the average age of Jira issues based on the provided JQL query.

    :param jql_query: JQL query string
    :param resolved: Flag indicating whether to consider resolved issues (default is True)
    :return: Average age in days
    """
    try:
        jira_options = lasso_authenticate()

        response = requests.get(
            f'{jira_options["server"]}/rest/api/latest/search',
            headers=jira_options['headers'],
            params={"jql": jql_query},
        )

        response.raise_for_status()
        issues = response.json()["issues"]

        total_age = timedelta()
        current_date = datetime.now()

        for issue in issues:
            created_date_str = issue["fields"]["created"]
            created_date = parse_iso_date(created_date_str)

            if resolved:
                resolved_date_str = issue["fields"]["resolutiondate"]
                resolved_date = parse_iso_date(resolved_date_str) if resolved_date_str else None
                if resolved_date:
                    age = resolved_date - created_date
                    total_age += age
            else:
                age = current_date - created_date
                total_age += age

        if issues:
            average_age = total_age / len(issues)
            return average_age.days
        else:
            return 0
    except Exception as e:
        return 0 
def parse_iso_date(date_str):
    """
    Parse ISO 8601 date strings with a flexible approach.

    :param date_str: ISO 8601 formatted date string
    :return: Parsed datetime object
    """
    try:
        # Attempt to parse with fromisoformat
        return datetime.fromisoformat(date_str)
    except ValueError:
        # If fromisoformat fails, handle timezone offset manually
        parts = date_str.split("+")
        base_date_str = parts[0]
        timezone_offset = f"+{parts[1]}" if len(parts) > 1 else "+0000"
        return datetime.strptime(base_date_str, "%Y-%m-%dT%H:%M:%S.%f") + timedelta(hours=int(timezone_offset[1:3]), minutes=int(timezone_offset[3:]))

def calculate_and_display_defect_ages(section_name, resolved_queries, unresolved_queries):
    """
    Calculate and display defect ages for a given section.

    :param section_name: Name of the section (e.g., Regression, Exploratory)
    :param resolved_queries: List of resolved queries for different priorities
    :param unresolved_queries: List of unresolved queries for different priorities
    """
    overall_resolved_age = 0
    overall_unresolved_age = 0
    
    for priority in ["Blocker", "Critical", "Others"]:
        resolved_query = resolved_queries[0] if priority == "Blocker" else resolved_queries[1] if priority == "Critical" else resolved_queries[2]
        unresolved_query = unresolved_queries[0] if priority == "Blocker" else unresolved_queries[1] if priority == "Critical" else unresolved_queries[2]

        resolved_age = calculate_average_age(resolved_query)
        unresolved_age = calculate_average_age(unresolved_query, resolved=False)

        overall_resolved_age += resolved_age
        overall_unresolved_age += unresolved_age


def fetch_jira_issues(jql_query, jira_options):
    try:
        response = requests.get(
            jira_options["server"] + '/rest/api/latest/search',
            headers=jira_options['headers'],
            params={"jql": jql_query},
        )

        response.raise_for_status()
        issues = response.json()["issues"]

        if issues:
            jira_data = []
            for issue in issues:
                jira_id = issue["key"]
                jira_title = issue["fields"]["summary"]
                jira_link = f'https://issues.labcollab.net/browse/{jira_id}'
                jira_data.append([f'<a href="{jira_link}">{jira_id}</a>', jira_title])

            df = pd.DataFrame(jira_data, columns=["Jira ID", "Jira Title"])
            return df
        else:
            print(f"No issues found for query: {jql_query}")
            return pd.DataFrame(columns=["Jira ID", "Jira Title"])  # Return an empty DataFrame
    except Exception as e:
        print(f"An error occurred: {e}")
        return pd.DataFrame(columns=["Jira ID", "Jira Title"])  # Return an empty DataFrame



def create_report_layout():
    columns = pd.MultiIndex.from_tuples([
        ('Regression', 'Blocker'),
        ('Regression', 'Critical'),
        ('Regression', 'Others'),
        ('Exploratory', 'Blocker'),
        ('Exploratory', 'Critical'),
        ('Exploratory', 'Others'),
        ('Overall', '')],
        names=['Metrics', 'Priority'])

    index = [
        'Resolved-Defect',
        'Unresolved-Defect'
    ]

    data = [[0] * len(columns) for _ in range(len(index))]

    df = pd.DataFrame(data, columns=columns, index=index)

    return df

# Calculate and display defect ages for regression and exploratory sections
calculate_and_display_defect_ages("Regression", regression_resolved_queries, regression_unresolved_queries)
calculate_and_display_defect_ages("Exploratory", exploratory_resolved_queries, exploratory_unresolved_queries)

# Create a report layout
report_df = create_report_layout()

# Fill in the report data with calculated values
report_df.at['Resolved-Defect', ('Regression', 'Blocker')] = calculate_average_age(regression_resolved_queries[0])
report_df.at['Resolved-Defect', ('Regression', 'Critical')] = calculate_average_age(regression_resolved_queries[1])
report_df.at['Resolved-Defect', ('Regression', 'Others')] = calculate_average_age(regression_resolved_queries[2])
report_df.at['Resolved-Defect', ('Exploratory', 'Blocker')] = calculate_average_age(exploratory_resolved_queries[0])
report_df.at['Resolved-Defect', ('Exploratory', 'Critical')] = calculate_average_age(exploratory_resolved_queries[1])
report_df.at['Resolved-Defect', ('Exploratory', 'Others')] = calculate_average_age(exploratory_resolved_queries[2])

report_df.at['Unresolved-Defect', ('Regression', 'Blocker')] = calculate_average_age(regression_unresolved_queries[0], resolved=False)
report_df.at['Unresolved-Defect', ('Regression', 'Critical')] = calculate_average_age(regression_unresolved_queries[1], resolved=False)
report_df.at['Unresolved-Defect', ('Regression', 'Others')] = calculate_average_age(regression_unresolved_queries[2], resolved=False)
report_df.at['Unresolved-Defect', ('Exploratory', 'Blocker')] = calculate_average_age(exploratory_unresolved_queries[0], resolved=False)
report_df.at['Unresolved-Defect', ('Exploratory', 'Critical')] = calculate_average_age(exploratory_unresolved_queries[1], resolved=False)
report_df.at['Unresolved-Defect', ('Exploratory', 'Others')] = calculate_average_age(exploratory_unresolved_queries[2], resolved=False)

# Calculate and set overall averages
overall_resolved_avg = (report_df.loc['Resolved-Defect', ('Regression', 'Blocker')] + 
                        report_df.loc['Resolved-Defect', ('Regression', 'Critical')] +
                        report_df.loc['Resolved-Defect', ('Regression', 'Others')] +
                        report_df.loc['Resolved-Defect', ('Exploratory', 'Blocker')] +
                        report_df.loc['Resolved-Defect', ('Exploratory', 'Critical')] +
                        report_df.loc['Resolved-Defect', ('Exploratory', 'Others')]) / 6

overall_unresolved_avg = (report_df.loc['Unresolved-Defect', ('Regression', 'Blocker')] + 
                          report_df.loc['Unresolved-Defect', ('Regression', 'Critical')] +
                          report_df.loc['Unresolved-Defect', ('Regression', 'Others')] +
                          report_df.loc['Unresolved-Defect', ('Exploratory', 'Blocker')] +
                          report_df.loc['Unresolved-Defect', ('Exploratory', 'Critical')] +
                          report_df.loc['Unresolved-Defect', ('Exploratory', 'Others')]) / 6

report_df.at['Resolved-Defect', ('Overall', '')] = overall_resolved_avg
report_df.at['Unresolved-Defect', ('Overall', '')] = overall_unresolved_avg

report_df_rounded = report_df.round(2)

print(report_df_rounded)

# Convert input dates to datetime objects
start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
end_datetime = datetime.strptime(end_date, "%Y-%m-%d")

# Extract month name from the start date
month_name = start_datetime.strftime("%B")

# Specify the path for the Excel file
directory = "defect"
if not os.path.exists(directory):
    os.makedirs(directory)
excel_file_path = os.path.join(directory, f"defect_age_{month_name}.xlsx")
# Save the report to file
report_df_rounded = report_df.round(2)
report_df_rounded.to_excel(excel_file_path, index=True)
print(f"Defect saved to {excel_file_path}")

