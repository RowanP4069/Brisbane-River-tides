# Setting up the Google Form and Google Sheet for flow reports

This project has a web page called "Report the flow", where people on the Brisbane River can report which way the water was moving. The page does not store reports itself. It sends each report to a Google Form, and Google saves the form's answers in a Google Sheet (a spreadsheet). Once a day, a script in this repository reads the reports that are meant to be public and saves them in the repository.

The form and the sheet are kept in the project owner's Google account, in Google Drive. They are not part of this repository, so this note describes how they are set up. Use it to check the setup, or to build a new form and sheet if the old ones are lost.

This note was written on 10 November 2026 and checked against the form and sheet in use on that date.

## How a report travels

1. The person fills in the report page and presses "Send report".
2. The page sends the report to the Google Form in two parts:
   - the public part: the time, the place as a distance up the river and which bank, the flow and water answers, the name the person chose, and a short device code;
   - the private part: the exact position, any notes, and the full device ID.
3. Google adds the report as a new row in the sheet's first tab, called "Form responses 1". This tab holds both parts, so it must stay private.
4. A second tab, called "public", copies only the time each report was received and the public part, using a formula.
5. Only the "public" tab is published on the web, as a CSV file (a plain-text table with commas between the values).
6. Once a day, the script `collect_reports.py` (run automatically by GitHub) downloads that CSV file, checks each report, and saves the accepted ones in the repository's `reports` branch. A branch is a separate line of files in the repository; this one holds only report data.

## Files in this repository that depend on this setup

- `build_report.py` builds the report page. Near the top, a setting called `FORM` holds the form's web address and the ID of each of its two questions.
- `web/report_template.html` is the page itself. Its function `buildReport()` decides what goes in the public part of a report.
- `collect_reports.py` is the daily script. Near the top, a setting called `PUBLIC_CSV` holds the web address of the published "public" tab.
- `data/reports_hidden.csv` lists reports to leave out, such as test reports and reports from pranksters.

## Step 1: Make the form

Create a new form in Google Forms and set it up as follows.

Title: Brisbane River flow reports

Description (shown to anyone who opens the form directly):

> Reports are sent from the Report the flow page: https://rowanp4069.github.io/Brisbane-River-tides/report.html - please use that page rather than this form. Published reports are shared under CC BY 4.0.

Questions: add exactly two, in this order. Choose the question type "Paragraph" for both, because the answers can be long.

1. A question titled `report`. It receives the public part of each report.
2. A question titled `private`. It receives the private part.

The page fills in both answers in a format called JSON, which is text that a program can read. People never type into these questions themselves.

Settings: open the form's "Settings" tab and expand the "Responses" section. Make sure that:

- the form does not collect email addresses;
- people do not have to sign in to a Google account to send a response;
- people are not limited to one response each.

Finally, make sure the form is published and accepting responses.

People sending a report never see the form. The report page sends to it in the background. Google does not let another website read the form's reply, so the page cannot confirm that a report arrived; it can only say that it sent one.

## Step 2: Connect the report page to the form

The report page needs three things from the form: its sending address, and an ID for each of the two questions. They go in the `FORM` setting in `build_report.py`.

The sending address. Open the form the way a respondent would see it. Its address ends in `/viewform`. Replace that ending with `/formResponse`. The result looks like this, where `<form id>` is a long string of letters and numbers:

```
https://docs.google.com/forms/d/e/<form id>/formResponse
```

The question IDs. Each question has an ID made of the word `entry`, a full stop, and a number, for example `entry.760987619`. To find them:

1. In the form editor, open the menu marked with three vertical dots, and choose "Get pre-filled link".
2. Type any text into both questions, then press "Get link" and copy the link.
3. The copied link contains one `entry.` followed by a number for each question, in the same order as the questions. The first one is for `report`, and the second is for `private`.

If the form is ever copied or rebuilt, the new form has a different address and different question IDs, so all three values must be updated. If the address in `FORM` is left empty, the page still works, but it sends nothing and tells the person it is in test mode.

## Step 3: Set up the sheet

Link a sheet to the form. In the form editor, open the "Responses" tab, choose "Link to Sheets", then "Create a new spreadsheet". Name it "Brisbane River flow reports (responses)". Google creates a tab called "Form responses 1" with three columns: "Timestamp", "report" and "private".

Set the time zone. In the sheet, open the "File" menu, choose "Settings", and set the locale to "Australia" and the time zone to "(GMT+10:00) Brisbane". The daily script treats each timestamp as Brisbane time (Australian Eastern Standard Time, with no daylight saving), so a different time zone would put every report at the wrong time.

Add the "public" tab. Add a new tab and name it exactly `public`. In its first cell (A1), enter the formula below, and leave every other cell on the tab empty:

```
=QUERY('Form responses 1'!A:B, "select A, B where A is not null label A 'submitted_aest', B 'report' format A 'yyyy-mm-dd hh:mm:ss'", 1)
```

This formula:

- copies only the first two columns (the timestamp and the public part), never the private part;
- skips empty rows;
- names the two columns `submitted_aest` and `report`, which are the names the daily script looks for;
- writes each timestamp in the form 2026-11-10 09:05:00, which is the form the daily script reads.

The formula refers to whole columns (`A:B`) on purpose. An earlier version referred to a range starting at row 2. Google moved that range down by one row each time a report arrived, so the first report was left out of the "public" tab.

## Step 4: Publish only the "public" tab

In the sheet, open the "File" menu, then "Share", then "Publish to web".

1. In the "Link" section, choose the tab named "public", not "Entire document", and choose the format "Comma-separated values (.csv)".
2. Open "Published content and settings". Check that it also names only the "public" tab, and leave "Automatically republish when changes are made" ticked.
3. Press "Publish", and confirm when Google asks if you are sure. That confirmation box did not appear in the browser built into the Claude app, and the sheet stayed unpublished. If pressing "Publish" seems to do nothing, do this step in an ordinary web browser.

Warning: publishing "Entire document" would put every report's exact position and notes on the open web.

Copy the link Google gives you into the `PUBLIC_CSV` setting in `collect_reports.py`. The link ends with `gid=` and a number. That number identifies the "public" tab.

To check that only the right tab is published:

- Open the link. It should download a CSV file whose first line is `submitted_aest,report`.
- Change the number after `gid=` to the number of the "Form responses 1" tab, and open that link. It should be refused with the error "401 Unauthorized". You can find a tab's number by clicking the tab and looking at the end of the sheet's address in the browser: it ends with `#gid=` and the number.

After a change, Google can take 10 minutes or more to update the published copy.

## Step 5: Test the whole chain

1. Build the page by running `python build_report.py`. It writes `output/report.html`.
2. Open that file in a browser and send a test report.
3. Check that the report appears as a new row in the "Form responses 1" tab and in the "public" tab.
4. Wait about 10 minutes, then run `python collect_reports.py --out <folder>`, where `<folder>` is a copy of the repository switched to the `reports` branch. The script prints how many reports it accepted, and the reason for leaving out any others. Check that the test report was accepted.
5. Hide the test report from the public record. Add a new line to `data/reports_hidden.csv` with the test report's timestamp, exactly as it appears in the `submitted_aest` column, in the first column. Leave the second column (`device`) empty, and put a short reason, such as "test report", in the third.

## What is only in Google Drive

The private part of every report (exact positions, notes and full device IDs) exists only in the "Form responses 1" tab of the sheet. The repository holds only the public part. To avoid losing the private part, download a copy of the sheet now and then (open the "File" menu, then "Download"). Keep the copy somewhere private. Do not add it to this repository, because the repository is public.
