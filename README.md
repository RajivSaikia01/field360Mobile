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

## Application sheet: when `snapshot_date` is the day the status changed
With `application_number` (one row per application) the date column can be **the day the application reached that status**,
either as one row for every status change, or as one row per application with its latest status and that day. The app reads the
file this way when it has **more than 7 different dates and applications do not repeat a status**. (In a snapshot file every
application repeats its status on every date, so it is read as snapshots. A file whose rows all carry one date is a single
snapshot with no history.)

The stage an application was in *before* its first recorded status is not in such a file, so the app takes it as **Enroll** from
the application date (as **Active** if the first status is **Closed**). Then:
- **Pending, Disbursed and Rejected are exact at every month-end**, so **Carried over** (pending at the start of a month, and
  what became of them) is right. In my test, rebuilt from only each application's latest status it found all 2,188 truly
  carried-over applications and 13 extra (99.4% precision).
- The **Movement** tab is back (opening, in, out, closing by stage, and the biggest moves). With a row for **every** status
  change it is exact. With only the latest status per application, where an application moved *from* before its recorded
  status is an assumption, and the screen says so.
- The Data sources check and `update_data.py` say how the file was read and how many applications had an assumed start.
With counts (`applications` column) it works as before, comparing one snapshot with the next (an estimate of the moves).

## LD (loan disbursement) sheet: the columns
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

## Application sheet: two ways to send it
Every row has `snapshot_date, branch_id, cre_id, cre_name, center_id, center_name, application_date, status`, plus **one** of:

- **`applications` + `applied_amount`**: a count per row (how many applications of that branch, SFO, center and application date
  were in that status on that snapshot date, and their total amount). Movement is then an estimate.
- **`application_number` + `applied_amount`**: one row per application per snapshot, with the same `application_number`
  (also read as `application_id`, `app_number`, `application_no`, `app_id`) every time that application appears, and
  `applied_amount` the amount of that one application. Movement and Carried over then use the real change of each
  application between snapshots.

Send one style or the other in a sheet. Either way every snapshot must list every application in the pipeline, including
Disbursed (A, Y) and Rejected (X), and Movement and Carried over need at least two `snapshot_date` values. A file with several
snapshot dates and neither `application_number` nor `applications` is **refused**, because the same application in two
snapshots cannot be told from two different applications.

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

**Sample account IDs** (the sample data): HO users `S012595` and `S014020`; a regional manager `E00019`; unit users
`E00001`, `E00039`, `E00069`, `E00098` and the others on the sample `users` sheet.

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
