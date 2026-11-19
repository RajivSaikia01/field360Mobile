# Field360 mobile app (UI acceptance)

A mobile app prototype that runs entirely in the browser. It opens with the Excel data already loaded, works on
**Android (Chrome)** and installs like a normal app.

> **Privacy:** the data in `index.html` and `field.html` is readable by anyone who can open the site. On a public
> repository that means everyone. Use test or masked data for a public site.

## Open it
| Who | Link |
|---|---|
| Phone | `https://YOURNAME.github.io/REPO/?clean=1` |
| Computer (phone-style view) | `https://YOURNAME.github.io/REPO/?app=1&clean=1` |
| Field version | `https://YOURNAME.github.io/REPO/field.html?clean=1` |

`?clean=1` hides the small presenter tab on the left edge (it switches role, access and screen).
`?app=1` shows the phone layout, as a centred column, on a computer.

## Who is signed in (the view)
The app opens as a **Unit Manager** of one unit. To look at it as someone else, open **Account** (tap the avatar, top
right) and choose a view under **View as**: Unit Manager (one unit), Zonal Head (one zone), Region Manager (one
region), HO member or Audit staff (whole organisation). Each changes the role and the area together, like a
different signed-in user.

To open straight into a view, add `view=` to the link, for example
`https://YOURNAME.github.io/REPO/?clean=1&view=zh` (`um`, `zh`, `rm`, `ho` or `audit`). A reload in the same tab
keeps the view you chose.

## Field Visit (not the HO one)
Field Visit reads two sheets of the data workbook: `process_and_subprocess` (columns `process_name`, `sub_process_name`)
and `field_visit` (the visits). The **Process** select lists the processes, and the **Sub-process** select next to it
lists only the sub-processes of the chosen process, in the Visits and Summary filters and in the Log a visit form.

**Date and month:** the bar at the bottom opens the same Viewing sheet as the other modules: **Daily** (pick a day) or
**Month to date** with the month chips. The current month counts from the 1st to the latest date; an earlier month
counts the whole month.

**Top block: PL and RP.** The top of the Visits and Summary tabs shows a **PL VISIT** row and an **RP VISIT** row, each with
its **Visits, Region, Unit and Branch** visits, worked out from that process's visits only. A place is counted once for
each person and day within each: three PL visits to one branch in a day are 3 PL visits but 1 PL branch visit, and an RP
visit to the same branch that day is 1 RP visit and 1 RP branch visit as well (a person is `created_by`). Choose a
process and the block shows just that row; for any other process it shows its visits only.

**Summary:** the number of visits, with Process, Sub-process, Area, Person and Month views. The Process view lists each
process with its sub-processes (highest first, unused ones dimmed), the Sub-process view ranks every sub-process with its
process underneath, and the Area, Person and Month views count visits by area, by person and by month. A person sees
every visit inside the areas they own.

**Filters:** the Process and Sub-process filters are phone-style pickers: tap the field and a bottom sheet opens with a
tick list (the long sub-process list has a search box). The Sub-process field stays dimmed until a process is chosen.

## Nothing is made up
`index.html` and `field.html` are **clean pages with no data inside**. Until you load your files the app shows its built-in demo.
Once your geography is loaded, **only your files are shown**: a sheet you have not uploaded (or an empty one) shows nothing, and
there are no invented SFOs, centers, customers, visits or figures. A month with no rows in your file shows nothing for that month.
Every sheet you load replaces what was there; with `--sheet all`, a sheet that is missing from the workbook is cleared.

**Every figure is filtered by `unit_id`.** FTOD, LD, Demand vs Collection and Application each carry a `unit_id`, a unit's totals
are the rows with its `unit_id`, and a unit manager (users sheet, same `unit_id`) sees only that unit.

**Which column is the date** (each screen filters on it): FTOD `as_of` (the FTOD date; cleared status in
`as_of_yesterday_ftod_cleared_status`), LD `disbursement_date`, Demand vs Collection `date`, Application `application_date`,
Field Visit `visit_date`.

## FTOD
**The columns.** `as_of` is the **FTOD date**: the day the loan went FTOD (first time overdue). `as_of_yesterday_ftod_cleared_status`
says whether that FTOD is cleared (TRUE or FALSE). `created_on` is not used. If the file also has `ftod_cleared_date`, a loan
counts as cleared on a chosen day only when that date is on or before it.

**The date you choose.** FTOD has a date only (no Month to date). For the date you pick, say the 18th:
- **BD** = the FTOD from the 1st of the month to the day before (1st to 17th).
- **New** = the FTOD on the chosen date (the 18th).
- **Collected** = the part of BD and New that is cleared.
- **Not clear** = the rest, so BD + New − Collected = Not clear.

**No loan is skipped.** A loan with no `loan_id` is counted as its own loan. Each FTOD date of a loan is a case of its own, and two
rows for the same loan and date count once. A loan on a branch that is not in the geography sheet is kept under the unit in its
`unit_id`, on a branch shown as "(not in geography)". Only rows marked `is_deleted`, and loans whose branch **and** `unit_id` are
both unknown, are left out, and the Data sources check names them. A date after today is a typo: it never counts as the last day,
and its loan is kept, counted from the last valid day.

**The "Sep FTOD cleared" tab** (last month's loans cleared this month) needs a cleared date; with only the TRUE/FALSE flag it
cannot show real numbers.

## Dates, LD and the application funnel
- **The date range** on every screen runs to the last day of the data. The date picker runs to **yesterday** (or to the last data
  day if that is later). With no file loaded the app opens on yesterday. The quick chips follow the calendar: data to yesterday is
  labelled **Yesterday**; older data is labelled "Latest · 18 Nov".
- **A date after today** is treated as a typo. In Application and LD the row is left out and the check says so; in FTOD the loan
  is kept. No dataset can move "today" past the real calendar day.
- **LD:** the date of a row is **`disbursement_date`** (a single day, Month to date and past months all filter on it). `as_of` is
  the day the file was extracted and is optional: if two rows have the same branch, SFO, center and `disbursement_date`, rows
  with the same `as_of` are added together and the latest `as_of` is used. A file with only `as_of` still works, and a file of
  running month totals is still recognised when `as_of` is the date.
- **Application:** every filter (a day, Month to date, a past month) works on `application_date`.
- In the Application funnel, each stage has a **Now at** line with the status-wise numbers (for example *Enroll (R)*, *Bureau
  Check (B)* under Enrolment; *Pre Sanction QC (S1)* and *Pre Sanction Credit (P1, S2, S3, S4)* under Pre-sanction), in Count,
  Amount and Percent, and a line for Draft and Rejected, which are outside the funnel.

## Units: `unit_id` in the data files
FTOD, LD, DC and the applications each have a **`unit_id`** column, and the unit of a branch is taken from it. A unit's totals
are the totals of the rows that carry its `unit_id`; the branches of the unit are the branches whose rows carry it, followed
by the SFOs (`cre_id`) and centers where the files have them. A user sees the unit assigned to them (users sheet) and its
branches below it. If the geography sheet puts a branch under a different unit, **the `unit_id` in the data is used**, and the
Data sources screen ("Branches and their units") says how many branches differ. A `unit_id` must be the `geo_id` of a unit in
the geography sheet, otherwise it is ignored; a branch whose rows name more than one unit gets the most frequent one.

## Application sheet
One row for each application, with its **current** status: `application_number, application_date, customer_id, customer_name,
branch_id, center_id, center_name, cre_id, cre_name, status, applied_amount, sanctioned_date, sanctioned_amount, unit_id`
(`sanctioned_date` and `sanctioned_amount` are not used).
- **Punched** counts applications by `application_date` (the month and date filters) and shows the funnel, in the stages of the
  `status_codes` sheet: 1 Enrolment (R, B), 2 Group training (C1, G1), 3 Pre-sanction (S1, P1, S2, S3, S4), 4 Sanctioned (S),
  5 Disbursed (A, Y). Draft (D) and Rejected (X) are outside the funnel. S2, S3 and S4 are shown as Sanctioned but sit in stage 3.
- **Carried over** takes the applications with an `application_date` in the month **before** the one you are viewing and shows
  what became of them: disbursed, rejected, still pending (and in which stage), with a list of the pending ones.
- There is no Movement tab. Use the status **codes** in the file: the description *Pre Sanction Credit* is shared by P1, S2, S3
  and S4 and is read as P1. Older files with `snapshot_date` or an `applications` count column are still read.

## Users: Employment Status
Columns: `EMPLOYEECODE, Employee Name, Employment Status, unit_id, Unit, is_ho_user`. Only users whose Employment Status is
Active (or blank) can sign in; anyone else sees "This account is not active". In `field_visit`, `created_by` is the
`EMPLOYEECODE` of the user; the app shows that user's name (the code if the person is not in the users sheet).

## LD (loan disbursement) sheet: the columns

The first column is **`disbursement_date`**, the day the loans were disbursed. `as_of` (the extract day) is optional.
`as_of, branch_id, unit_id, region_id, cluster_id, zone_id, cre_id, cre_name, center_id, center_name, count_le_16k, count_17k_40k,
count_41k_60k, count_61k_80k, count_81k_1l, count_gt_1l, grand_total, tenure_2y_gt_70k, tenure_3y_gt_70k, tenure_1y, tenure_2y,
tenure_3y, new_loans, repeat_le_50k, repeat_gt_50k, new_amount, repeat_amount, nqa, qa, net_loans, net_amount, entity`
(a header written `grand total` with a space is read too). The `count_` columns are loans by amount; `grand_total` is the
number of loans and `net_amount` the amount disbursed. `unit_id`, `region_id`, `cluster_id`, `zone_id`, `entity` and `net_loans`
may be in the sheet but are not read (the geography sheet defines the hierarchy). Optional: `repeat_gt_50k_amount` (BPR shows
the amount of repeat loans above 50K only if it is there). The LD screen no longer has "Loans with the organisation", so the
`loan_1_with_org` ... `loan_gt_3_with_org` columns are not needed (if they are present they are ignored), and the data check
for them is gone. Files that still use the older `amt_...` names for the buckets are read too.
`update_data.py` and `trim_data.py` work with this structure unchanged: both use the `as_of` date and the app's own reader.

## Users and sign-in (the `users` sheet)
Add a sheet named **users** to the data workbook with these columns: `EMPLOYEECODE`, `Employee Name`, `unit_id`, `Unit`,
`is_ho_user`. Then run `update_data.py` as usual.

- A user signs in with **only their account ID** (the `EMPLOYEECODE`). There is no password. Capital letters and spaces
  around the ID do not matter. An ID that is not in the sheet is refused.
- A user lands on the geography and data of the place in `unit_id` and **cannot see or open anything outside it**: Home,
  the modules, search, offices, visits and every total follow that place and everything below it. `unit_id` can be a
  unit, a region or a zone, or several of them separated by commas or the word "and".
- `is_ho_user` = **YES** gives the whole organisation (write `unit_id` as `HO and <head office geo_id>` if you like) and
  access to Data sources. Everyone else cannot change their role or area, use the "View as" switch or open Data sources.
- A user whose `unit_id` is not in the geography sheet is skipped, and the updater names them.
- With no users sheet, anyone can sign in (the old prototype behaviour).

**Sample account IDs** (the sample data): HO users `S012595` and `S014020`; a regional manager `E00019`; unit managers `E00001`, `E00039`, `E00069`, `E00098` and the others on the sample `users` sheet; `E00469` is marked Resigned and cannot sign in.

**Important: this is a gate inside the app, not security.** The data of every user is part of the app file, so anyone who
can open the file (or the page source) can read all of it. Do not publish real confidential data on a public GitHub
site. For real protection the data has to be served by a backend after a real sign-in.

## Very large Excel files (Node.js runs out of memory)
`update_data.py` needs memory in proportion to the **heaviest sheet** it reads: about **25 times that sheet's size when the
file is opened** (the 79 MB `ld` sheet of the sample needs about 2 GB). Do these in order:

1. **See which sheet is heavy** (changes nothing; needs only Python):
   ```
   python trim_data.py data/my-data.xlsx --report
   ```
   It lists each sheet's opened size, its rows, the memory it needs, and the `--memory` value to use.
2. **Update one sheet at a time** instead of the whole file. Each step reads only that sheet and keeps everything else
   already in the pages, so the update needs only the heaviest sheet's memory, not the whole file's:
   ```
   python update_data.py data/my-data.xlsx --sheet geography          (always first)
   python update_data.py data/my-data.xlsx --sheet process_and_subprocess users
   python update_data.py data/my-data.xlsx --sheet ld
   python update_data.py data/my-data.xlsx --sheet dc field_visit hr applications ftod aop
   ```
   or all of them, one after the other, in one command: `python update_data.py data/my-data.xlsx --sheet all`.
   Sheet names: `geography, process_and_subprocess, users, ftod, ld, aop, hr, applications, dc, field_visit`.
   Add `--memory 8192` (about half your RAM; Node must be 64-bit: `node -p "process.arch"` says `x64`).
   A step that fails leaves the steps before it saved; fix it and run just that sheet again.
3. **Make the heavy sheet smaller.** The app keeps only the **last three months** of `ld`, `dc` and `field_visit`, so older
   rows are wasted. Make a smaller copy (never changes your original; keeps one extra month; keeps any row whose date it
   cannot read):
   ```
   python trim_data.py data/my-data.xlsx          (writes data/my-data-trimmed.xlsx)
   ```
   If the heavy sheet is another one, remove columns and blank rows you do not need in Excel (delete, do not just clear,
   the empty rows at the bottom) and save as `.xlsx`.
4. If the final check (it opens the updated pages and loads all the data at once) runs out of memory, add `--no-verify`
   and open the pages in a browser to check them yourself.

## "Access is denied" when the updater saves index.html (Windows)
The updater now clears the Read-only flag, retries, and writes over the file if needed. If it still cannot save, it stops
without changing anything and says why. Check, in order:
1. **Read-only:** in the folder run `attrib -R index.html field.html`.
2. **File open elsewhere:** close editors, previews and live-server tools, and stop any `python -m http.server`.
3. **Antivirus, OneDrive or Windows "Controlled folder access"** blocking Python: pause it, allow `python.exe`, or copy the
   whole folder to a simple path such as `C:\f360` and run it there.
4. Delete leftover `index.html.tmp` and `field.html.tmp` files. Test write access with
   `python -c "open('index.html','a').close(); print('writable')"`.

## Install on Android (Chrome)
Open the link in Chrome, then either tap **Install Field360 on this phone** on the sign-in screen, or use the menu
(three dots) and choose **Install app**. It then opens from its own icon, full screen. The phone's Back button or
swipe goes to the previous screen. Press Back twice on Home to exit. It also opens offline after the first visit.
Installing needs the secure `https://` link that GitHub Pages gives you.

## Publish on GitHub Pages
1. Create a repository and upload every file in this folder (keep the folder structure).
2. **Settings > Pages > Source: Deploy from a branch > main > / (root) > Save.**
3. After a minute or two the site is at `https://YOURNAME.github.io/REPO/`.

## Update the data
1. Put your Excel file in `data/` (start from `data/field360-input-data-template.xlsx`).
2. Install **Node.js** (the LTS version, from nodejs.org) once. Python 3.8 or newer is needed too.
3. Run:
   ```
   python update_data.py data/your-file.xlsx
   ```
   It reads the file with the app's own loader, shows what it found, asks for confirmation, writes the data into
   `index.html` and `field.html`, then opens them in a simulated browser to check. If the check fails it puts the
   original files back.
4. Upload the updated `index.html` and `field.html` to GitHub (replace the old ones). The site refreshes in a minute.

Useful options: `--check` (only check the file), `--yes` (do not ask), `--backup` (keep `.bak` copies),
`--html FILE ...` (update other files), `--label NAME` (the file name shown in the app).
A large file takes a minute or two and needs a few GB of free memory. If Node.js runs out of memory, close other programs
or add `--memory 4096` (megabytes, below the memory your computer has). Every sheet in the Excel file replaces what was there: a sheet that is empty or
missing is not carried over (the app shows its built-in sample figures for it).

### Optional: let GitHub update the site
Upload your workbook as `data/field360-data.xlsx`. The workflow in `.github/workflows/update-data.yml` runs the same
updater and commits the new `index.html` and `field.html`. Turn on **Settings > Actions > General > Workflow
permissions > Read and write permissions** first. (This workflow could not be run before it was handed over,
so check the **Actions** tab after your first upload.)

## Files
| File | What it is |
|---|---|
| `index.html`, `field.html` | the full app and the field version, with the data inside |
| `manifest.webmanifest`, `sw.js`, `icon-*.png` | what lets Android install it and open it offline |
| `update_data.py` | puts the Excel data inside the two app files |
| `data/` | the template workbook, and where your own workbook goes |
