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
A large file takes a minute or two. Every sheet in the Excel file replaces what was there: a sheet that is empty or
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
