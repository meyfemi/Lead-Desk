# Setup

This guide gets Lead Desk running on a Mac or Windows computer. It takes about 15 minutes.

## Before you start

Have these ready:

- **The project folder.** Copy it from a computer that already has it (zip it, then send it
  by USB, AirDrop or Google Drive), or clone it from Git.
- **Three API keys:**
  - **Apify** (finds businesses): [console.apify.com](https://console.apify.com) → Settings → API & Integrations
  - **Claude** (writes emails): [console.anthropic.com](https://console.anthropic.com) → Settings → API keys. Add credit under Billing.
  - **Mailtrap** (sends emails): [mailtrap.io](https://mailtrap.io) → Settings → API Tokens

> If you copied the folder from another computer, it already has your keys in a hidden
> file called `.env`. You can skip step 3 below.

---

## Mac

Open **Terminal** (press Cmd + Space, type `Terminal`, press Enter).

**1. Install Python.** Download the macOS installer from
[python.org/downloads](https://www.python.org/downloads/) and run it. When it finishes,
double-click **Install Certificates.command** in the Finder window that opens.

Open a new Terminal window and check it worked:

```bash
python3 --version
```

**2. Install the packages.**

```bash
cd ~/Development/"Lead Scraper Apify"
python3 -m pip install -r requirements.txt
```

(Change the path if your project folder is somewhere else.)

**3. Add your settings.**

```bash
cp .env.example .env
open -e .env
```

Fill in your details and keys (see [Your settings](#your-settings) below), then save.

**4. Start Lead Desk.**

```bash
./start-ui.sh
```

Your browser opens at **http://127.0.0.1:8765**. Keep Terminal open while you use it.
Press **Ctrl + C** to stop.

If you see `permission denied`, run `chmod +x start-ui.sh` once and try again.

---

## Windows

Open **PowerShell** (click Start, type `PowerShell`, press Enter).

**1. Install Python.** Install **Python Install Manager** from the Microsoft Store, or
download Python from [python.org/downloads](https://www.python.org/downloads/). Open a new
PowerShell window and check it worked:

```powershell
python --version
```

If it asks to download Python or add it to your PATH, say **yes**.

**2. Turn on UTF-8 (important).**

```powershell
setx PYTHONUTF8 1
```

Then **close all PowerShell and VS Code windows and reopen them**. Without this, business
names and emails with special characters (like ₦) break.

**3. Install the packages.**

```powershell
cd "$HOME\Development\Lead Scraper Apify"
python -m pip install -r requirements.txt
```

**4. Add your settings.** Open the project folder in **VS Code**, copy `.env.example`,
name the copy `.env`, and fill it in (see [Your settings](#your-settings) below).

Don't use Notepad. It may save the file as `.env.txt`, and Lead Desk won't find it.

**5. Start Lead Desk.**

```powershell
python ui\server.py
```

Your browser opens at **http://127.0.0.1:8765**. Keep PowerShell open while you use it.
Press **Ctrl + C** to stop.

---

## Your settings

Your `.env` file should look like this:

```
COMPANY_NAME=Your Company
COMPANY_TAGLINE=One line about what you do
SENDER_NAME=Your first name
MAIL_FROM_ADDRESS=you@yourcompany.com
DEFAULT_LOCATION=Lagos, Nigeria
DEFAULT_CATEGORIES=restaurant, clinic, law firm
APIFY_API_KEY=your-apify-key
MAILTRAP_API_KEY=your-mailtrap-key
ANTHROPIC_API_KEY=your-claude-key
```

- `MAIL_FROM_ADDRESS` must use a domain you've verified in Mailtrap.
- `COMPANY_TAGLINE` is optional.
- **Keep `.env` private.** It holds your live keys. Never share it or upload it.

To set up Lead Desk for a different business, see [CUSTOMIZING.md](CUSTOMIZING.md).

---

## Check it works

1. At the bottom of the sidebar, the **Apify**, **Mailtrap** and **Claude** dots are all
   **green**.
2. Open any lead and click **Dry run**. It shows what would be sent, without sending anything.
3. On **Discover**, choose **Research & draft only** and find 2 or 3 leads. When it
   finishes, open the new leads and read the emails.

If all three work, you're ready.

> **Using two computers?** Your leads are stored in the `leads/` folder on each computer,
> and the two copies don't sync. Pick one computer as your main one, or copy `leads/`
> across when you switch.

---

## Common problems

| Problem | Fix |
|---------|-----|
| `python` or `python3` not found | Open a new terminal window. If it still fails, reinstall Python. |
| A sidebar dot is red | That key is missing from `.env`. Check the file is called `.env` (not `.env.txt`) and sits in the main project folder. Then reload the page. |
| Browser can't connect, or "Address already in use" | Another app is using the port. Start with `--port 9000` and open http://127.0.0.1:9000. |
| `CERTIFICATE_VERIFY_FAILED` | Mac: run **Install Certificates.command** from Applications → Python. Then run the package install step again. |
| **Enrich** always says "nothing new found" (Windows) | UTF-8 is off. Repeat Windows step 2 and reopen your terminal. |
| **Find leads** is greyed out | Run the package install step again, then restart Lead Desk. |
| "ANTHROPIC_API_KEY was rejected" | Your Claude key is wrong or revoked. Check it at console.anthropic.com. |
| Credit, billing or rate limit error | Add credit at console.anthropic.com, or wait a minute and try again. Leads already found are kept. |
| Emails fail to send | Check that `MAIL_FROM_ADDRESS` is on a domain verified in Mailtrap. On Windows, run Windows Update if curl is missing. |

---

## Optional: the `/find-leads` command

You don't need this to use Lead Desk. It lets you run the same workflow by typing
`/find-leads` in Claude Code in a terminal.

1. Windows only: install [Git for Windows](https://git-scm.com/downloads/win).
2. Install Claude Code:
   - Mac: `curl -fsSL https://claude.ai/install.sh | bash`
   - Windows: `irm https://claude.ai/install.ps1 | iex`
3. In the project folder, run `claude`, sign in, then type `/find-leads`.

> **This sends real emails.** To draft without sending, type:
> `/find-leads Stop after Step 5 and don't send any emails.`
