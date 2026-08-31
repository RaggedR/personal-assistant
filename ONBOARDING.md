# ONBOARDING.md — instructions for Claude, not for the human

**You are Claude. This document is addressed to you.** A person has asked you
to help them set up the `pa` CLI (Gmail, Google Calendar and Google Contacts
from the command line). Your job is to walk them through it, one step at a
time, doing every technical part yourself.

Do not hand this file to the person. Do not summarise it to them. Read it, then
start guiding.

---

## THE ONE RULE

**Give exactly one step at a time. Then stop and wait for their reply.**

This is the single most important instruction in this document, and it is the
one you will be most tempted to break. Your instinct is to be efficient and
present the whole path at once. Resist it. A person following browser
instructions cannot hold ten steps in their head, and when step 4 looks
different from your description they will not know that steps 5–10 are now
wrong.

### Wrong

> Now let's set up Google Cloud:
> 1. Go to console.cloud.google.com and create a project
> 2. Enable the Gmail, Calendar and People APIs
> 3. Configure the OAuth consent screen and add yourself as a test user
> 4. Create a Desktop app OAuth client and download the JSON
> 5. Then run `pa auth login`
>
> Let me know when you're done!

### Right

> Open this URL in your browser:
>
> https://console.cloud.google.com/projectcreate
>
> You should see a form headed **New Project** with a "Project name" field.
> Type `pa-cli` into it, leave everything else alone, and click **CREATE**.
>
> Tell me when the project has been created, or tell me what you see if the
> page looks different from that.

One action. One URL. What they should see. An invitation to report a mismatch.
Then silence until they answer.

### What counts as one step

- One URL to open, **or**
- One menu path to follow, **or**
- One form to fill in, **or**
- One button to click, **or**
- One thing for you to run and report back on.

A step may contain several *keystrokes* in one form ("type `pa-cli` in the name
field and click CREATE"), because that is one coherent action in one place. It
may never contain two different pages.

### The stop discipline

After every step, your message must end with a question or a request for
confirmation, and you must send nothing further until they reply. Every step in
the stages below is marked `→ STOP`. That marker means: end your message there.

The only exception is when they have explicitly told you they know a section
well and want it compressed. Even then, never merge steps across two different
websites.

---

## When they get lost

They will get lost. Web UIs change, and Google's in particular is mid-migration
between two designs, so what you describe may not match what they see.

When a person says "I don't see that", "this looks different", or gives a vague
answer, **do not guess and do not repeat yourself louder.** Ask for a
screenshot:

> No problem — the Google Console has changed layouts recently. Can you take a
> screenshot of what you're seeing and paste it here?
>
> On a Mac: press **Cmd + Shift + 4**, drag a box around the window, then the
> image lands on your Desktop or clipboard — paste it straight into this chat.
> On Windows: press **Windows + Shift + S**, drag a box, then paste here.

You can see pasted images. Read the actual screen and re-orient them from
what is really there, rather than from what this document predicted. **Trust the
screenshot over this document.** These instructions were accurate when written;
the screenshot is accurate now.

If you are still unsure after a screenshot, say so plainly and ask them to
contact Robin, rather than sending them clicking around a console that controls
access to their email.

---

## Ground rules

1. **You do the technical work.** They should never be asked to run a command
   you could run yourself. The only things they do are: things in their browser,
   things requiring their password, and the two commands noted below that must
   run in their own terminal.

2. **Never ask them to paste a token, password or secret into this chat.**
   Chat transcripts are stored. When a secret must be typed, they type it into
   their own terminal or browser, never to you. Nothing on the main path asks
   for a secret; if you go on to Appendix A, this applies to the GitHub token.
   You verify success by running a status command, not by reading the secret.

3. **Probe before you ask.** Before asking "is Python installed?", run
   `python3 --version`. Before asking whether the tool is already set up, run
   `pa auth status`. Skip any stage that is already done, and tell them you are
   skipping it and why. Never make someone answer a question a command could
   answer.

4. **Be explicit by default, and never condescending.** Assume they can follow
   precise instructions but do not know this specific console. Name buttons in
   **bold** exactly as they are labelled. Give full URLs, not "go to settings".
   If they tell you they know a part well, believe them and compress it.

5. **Adapt to their operating system.** Detect it first (`uname -s`, or note if
   you are on Windows) and give only the relevant commands. Do not present three
   OS variants and make them choose.

6. **Tell them what a step is for, in one sentence.** "This next bit creates the
   Google credentials that let the tool read your mail" is worth eight words of
   context. A person who understands the goal recovers from surprises.

7. **Never invent a URL or button name.** If you do not know, say you do not
   know and ask for a screenshot. A confidently wrong click path in a console
   that governs their mailbox is worse than an admission of uncertainty.

8. **Keep a running sense of where you are.** If the conversation is
   interrupted, re-run the probes from Stage 0 to work out what is already done
   before resuming. Do not restart from the beginning.

---

## Opening message

Start roughly like this — adapt the wording, keep the specifics:

> I'm going to help you set up `pa`, a command-line tool that gives us access to
> your Gmail, Google Calendar and Contacts. Once it's working I'll be able to
> search your mail, draft replies and check your calendar directly.
>
> It takes about 20 minutes. Most of it is me running things; the parts you'll
> do are in your browser, clicking through Google's permission setup.
>
> Two things worth knowing up front:
>
> - I will **never** send an email without asking you first. The tool refuses to
>   send unless a specific confirmation flag is passed, and I won't pass it
>   without your explicit go-ahead on that specific message.
> - The tool cannot permanently delete your mail. The strongest thing it can do
>   is move a message to Trash, where Gmail keeps it for 30 days.
>
> I'll give you one step at a time and wait for you each time. If anything looks
> different from what I describe, just say so and paste a screenshot — the
> Google console changes its layout fairly often.
>
> Ready to start?

→ STOP. Wait for them.

---

## Stage 0 — Silent prerequisite check

Do this yourself before asking them anything. Run these and read the results;
do not narrate each one.

```bash
uname -s -m                  # OS and architecture (skip on Windows)
python3 --version            # need 3.10 or newer
git --version
command -v uv pipx brew      # which installers are available
echo "$PATH" | tr ':' '\n' | grep -c "$HOME/.local/bin"
pa --version                 # already installed?
```

That is the whole list. There is deliberately no GitHub check here: the
repository is public, so nothing in Stages 1–4 needs a GitHub account, the `gh`
CLI, or a token. Do not raise the subject.

Then tell them, in one short message, what you found. For example:

> You've already got Git and Python 3.12, so we can go straight to downloading
> the tool. Nothing to install first.

→ STOP. Confirm before proceeding.

If `pa --version` already works, jump to Stage 3 (Google authorisation) and
then Stage 4.

---

## Stage 1 — Clone the repository

Your job entirely. The repository is public, so this needs no GitHub account,
no login and no token — it works on a completely unauthenticated machine. Do
not send them to GitHub for anything.

### Step 1.1 — Clone

```bash
git clone https://github.com/RaggedR/personal-assistant.git ~/personal-assistant
```

If `~/personal-assistant` already exists, `cd` into it and `git pull` instead.

Report in one line:

> Downloaded the tool's source to `~/personal-assistant`.

→ STOP.

---

## Stage 2 — Install the tool

Your job entirely. Do not make them run any of this.

### Step 2.1 — Check Python

`pa` needs Python 3.10 or newer. You checked this in Stage 0.

If it is too old or missing: on macOS `brew install python@3.12`; on Windows
`winget install --id Python.Python.3.12 -e`; on Debian/Ubuntu
`sudo apt install python3 python3-venv` (they run the `sudo` one).

### Step 2.2 — Install

In order of preference. Note the `cd` — every command below assumes you are
in the cloned directory.

```bash
cd ~/personal-assistant

# Preferred: uv
uv tool install --editable .
```

If `uv` is absent, install it first (no admin password needed):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Then use the full path, not bare `uv`.** The installer puts it in
`~/.local/bin`, which is not on the PATH of the shell you are already in, so a
bare `uv` will report "command not found" seconds after a successful install:

```bash
~/.local/bin/uv tool install --editable .
```

Alternatives, in order:

```bash
pipx install --editable .

# Last resort, always works:
python3 -m venv .venv && .venv/bin/pip install -e .
# then the command is ~/personal-assistant/.venv/bin/pa
```

**Known trap:** on some Macs `pipx` is broken because Homebrew's Python 3.14
ships a mismatched `libexpat`. The symptom is an `ImportError` mentioning
`pyexpat` and `_XML_SetAllocTrackerActivationThreshold`. Do not try to fix it —
use `uv` instead.

### Step 2.3 — Make sure `pa` is on PATH

Both `uv` and `pipx` install to `~/.local/bin`. If that is not on their PATH,
`pa` will appear not to exist.

```bash
pa --version
```

If that fails but `~/.local/bin/pa --version` works, add it to their shell
profile — `~/.zshrc` on modern macOS, `~/.bashrc` on most Linux:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
```

Tell them, because their own terminal windows need it too:

> I've added `~/.local/bin` to your PATH. Any terminal windows you already have
> open won't know about it — close and reopen them, or run
> `source ~/.zshrc` in each.

### Step 2.4 — Confirm

```bash
pa --version
```

Then, optionally, run the test suite. It is fully offline and takes under a
second, and proves the install is sound before you attach their Google account
to it.

`pytest` is a development dependency and is **not** installed by
`uv tool install`, so do not run bare `python3 -m pytest` — on a clean machine
that fails with "No module named pytest", which looks like a broken install but
is not. Either run it in a throwaway environment:

```bash
cd ~/personal-assistant && ~/.local/bin/uv run --with pytest --with-editable . pytest -q
```

or simply skip it. `pa --version` succeeding is sufficient evidence to continue.
Never report "the tests failed" when what actually happened is that pytest was
absent.

Report:

> `pa` is installed and working. Now the only thing left is giving it
> permission to see your Google account — that's the fiddly part, and it's all
> in your browser.

→ STOP.

---

## Stage 3 — Authorise Google access

This is the longest stage and the one where they will get lost. Take it slowly.

Google requires two separate things, and it helps to say so once, briefly:

> Google wants two things: first we register an "application" (that's this
> tool), then you grant that application access to your account. About six
> clicks each. The screens are unhelpfully named but I'll point at exactly
> where to go.

**Important context for you:** Google is midway through migrating this console
from the old "APIs & Services → OAuth consent screen" design to a newer "Google
Auth Platform" design. Which one they see depends on the age of their project
and the rollout. Both are covered below. When in doubt, ask for a screenshot
and branch on what is actually there.

### Step 3.1 — Create a project

> Open this URL:
>
> https://console.cloud.google.com/projectcreate
>
> If this is your first time in Google Cloud it may ask you to agree to terms
> of service and pick a country — do that first.
>
> You should reach a form headed **New Project**. In the **Project name** field
> type:
>
> ```
> pa-cli
> ```
>
> Leave "Location"/"Organization" as whatever it defaults to, and click
> **CREATE**.
>
> After a few seconds a notification appears saying the project is ready. Tell
> me when you see it.

→ STOP.

### Step 3.2 — Make sure the project is selected

This trips people up constantly: they enable APIs on the wrong project and
nothing works later, with a confusing error.

> One thing to check before we go on. At the very top of the page, just right of
> the "Google Cloud" logo, there's a project picker showing a project name.
>
> Does it say **pa-cli**? If it says something else, click it and choose
> `pa-cli` from the list.

→ STOP.

### Step 3.3 — Enable the Gmail API

One API per step. Do not combine these three.

> Open this URL:
>
> https://console.cloud.google.com/apis/library/gmail.googleapis.com
>
> You should see a page titled **Gmail API** with a blue **ENABLE** button.
> Click it, and wait for the page to change.
>
> If instead of ENABLE you see "API enabled" with a **MANAGE** button, it's
> already on — that's fine too. Which did you get?

→ STOP.

### Step 3.4 — Enable the Calendar API

> Same again, different URL:
>
> https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
>
> Titled **Google Calendar API**. Click **ENABLE**.

→ STOP.

### Step 3.5 — Enable the People API

> Last one — this is for Contacts, so I can look up someone's address by name:
>
> https://console.cloud.google.com/apis/library/people.googleapis.com
>
> Titled **People API**. Click **ENABLE**.

→ STOP.

### Step 3.6 — Find out which console design they have

> Now open this URL:
>
> https://console.cloud.google.com/auth/overview
>
> Tell me which of these you see:
>
> **(a)** A page headed **Google Auth Platform** with a "Get started" button, or
> a left sidebar listing **Overview / Branding / Audience / Clients / Data
> Access**.
>
> **(b)** A page headed **OAuth consent screen** asking you to choose a **User
> Type** — "Internal" or "External".
>
> **(c)** Something else entirely — if so, paste a screenshot.

→ STOP. Branch on the answer.

### Step 3.7a — Newer console ("Google Auth Platform")

Follow this only if they answered (a).

> Click **GET STARTED**.
>
> First it asks for **App name** — type `pa`. Below it, **User support email** —
> pick your own address from the dropdown. Click **NEXT**.

→ STOP.

> Now it asks about **Audience**. Choose **External**.
>
> ("Internal" only exists if you're inside a Google Workspace organisation and
> is simpler when available — if Internal is offered and you're on a work
> account, pick that instead and tell me.)
>
> Click **NEXT**.

→ STOP.

> Now **Contact Information** — enter your own email address. Click **NEXT**.
>
> Then tick the box agreeing to the user data policy, and click **CONTINUE**,
> then **CREATE**.

→ STOP.

> Now in the left sidebar click **Audience**.
>
> Scroll down to a section headed **Test users** and click **+ ADD USERS**.
> Type your own Google email address, press Enter, then click **SAVE**.
>
> This matters: without your address in that list, Google will block your own
> login later with an "access blocked" error.

→ STOP. (Skip this sub-step if they chose Internal — Internal has no test users.)

Now continue at Step 3.8.

### Step 3.7b — Classic console ("OAuth consent screen")

Follow this only if they answered (b).

> Under **User Type**, choose **External**, then click **CREATE**.
>
> ("Internal" is simpler but only available on Google Workspace accounts. If
> it's offered and you're on a work account, pick it and tell me.)

→ STOP.

> Now a form headed **OAuth consent screen**. Fill in three fields:
>
> - **App name**: `pa`
> - **User support email**: choose your own address from the dropdown
> - **Developer contact information** (at the very bottom): your own address
>
> Ignore everything else — logo, domains, all optional. Click **SAVE AND
> CONTINUE**.

→ STOP.

> Next page is **Scopes**. Skip it entirely — don't add any. Just scroll down
> and click **SAVE AND CONTINUE**.
>
> (The tool asks for its own permissions when you log in, so there's nothing to
> do here.)

→ STOP.

> Next page is **Test users**. Click **+ ADD USERS**, type your own Google email
> address, press Enter, then **ADD**, then **SAVE AND CONTINUE**.
>
> This matters: without your address here, Google blocks your own login later.

→ STOP.

> Last page is a **Summary**. Nothing to do — click **BACK TO DASHBOARD** at the
> bottom.

→ STOP.

### Step 3.8 — Create the OAuth client

> Open this URL:
>
> https://console.cloud.google.com/apis/credentials
>
> Near the top click **+ CREATE CREDENTIALS**, and from the dropdown choose
> **OAuth client ID**.
>
> (On the newer console design this may instead be a **Clients** page with a
> **+ CREATE CLIENT** button — same thing.)

→ STOP.

### Step 3.9 — Choose Desktop app

This is the single most important click in the whole process. Getting it wrong
produces a `redirect_uri_mismatch` error much later, which is hard to trace back
to here.

> There's an **Application type** dropdown. Choose **Desktop app**.
>
> This one really matters — "Web application" looks like the obvious choice and
> will not work.
>
> A **Name** field appears; `pa` is fine. Then click **CREATE**.

→ STOP.

### Step 3.10 — Download the JSON

> A dialog appears headed something like **OAuth client created**, showing a
> Client ID and Client Secret.
>
> Click **DOWNLOAD JSON**. It saves a file to your Downloads folder with a long
> name starting `client_secret_`.
>
> Then click **OK** to close the dialog. You don't need to copy anything out of
> it — the file has everything.
>
> Tell me when it's downloaded.

→ STOP.

### Step 3.11 — Install the client file

Your job. Find the most recent download and install it:

```bash
ls -t ~/Downloads/client_secret*.json | head -1
pa auth setup-client "$(ls -t ~/Downloads/client_secret*.json | head -1)"
```

This validates the file and copies it to `~/.config/pa/client.json` with
owner-only permissions. If the glob finds nothing, ask them where their browser
saves downloads.

Then:

> Installed. You can delete that file from Downloads if you like — I've copied
> what's needed into a private config directory.

→ STOP.

### Step 3.12 — Log in

They run this one themselves. It opens a browser and waits, so it is better in
their own terminal where they can see it and interrupt it if needed.

> Last browser step. In your terminal, run:
>
> ```
> pa auth login
> ```
>
> Your browser will open and ask which Google account to use. Pick the one whose
> mail and calendar you want me to have access to.

→ STOP.

### Step 3.13 — Get past the "unverified app" warning

Warn them before it appears, or it looks alarming.

> You'll now see a scary-looking screen: **"Google hasn't verified this app"**.
>
> This is expected and correct. "This app" is the OAuth client *you* created ten
> minutes ago — Google's verification process is for apps distributed to
> strangers, and yours has exactly one user. There is nothing to verify.
>
> Click **Advanced** (small link, bottom-left), then click
> **Go to pa (unsafe)** at the bottom.

→ STOP.

### Step 3.14 — Grant the permissions

> Now Google lists what the tool wants: read and send mail, manage calendars,
> read contacts.
>
> Tick every checkbox — if you leave any unticked, the corresponding feature
> just won't work — then click **Continue**.
>
> The browser should end up on a plain page saying authentication succeeded, and
> your terminal should print something like "Authorised 'default'".

→ STOP.

### Step 3.15 — Verify for real

Your job. Run:

```bash
pa auth status
```

You want all three services showing `[ok  ]`:

```
  [ok  ] gmail     pa store (...)  their@email.com
  [ok  ] calendar  pa store (...)
  [ok  ] contacts  pa store (...)
```

Then prove it end to end with real data:

```bash
pa mail search 'is:unread' -n 3
pa cal list --from today --to +7d
```

Report what you found, using their actual data — this is the moment it becomes
real to them:

> It's working. You have 12 unread messages, and three things on your calendar
> this week — a meeting with Alex on Thursday at 4:30, and two others.

→ STOP.

If any service shows `[fail]` or `[none]`, go to the troubleshooting table
below. Do not proceed to Stage 4 with a broken service.

---

## Stage 4 — Teach their Claude to use it

The tool is installed, but *their* Claude does not yet know it exists or what
the safety rules are. Without this stage, their next session will reach for
whatever it can find and may not respect the sending rule.

### Step 4.1 — Ask permission to edit their config

> One last thing, and this one's for me rather than you. I'd like to add a note
> to your `~/.claude/CLAUDE.md` — the file of standing instructions I read at
> the start of every session — so that future-me knows this tool exists and
> knows never to send mail without asking you.
>
> May I?

→ STOP. Do not edit their configuration without asking.

### Step 4.2 — Append the block

Append this to `~/.claude/CLAUDE.md`, creating the file if needed. Do not
overwrite anything already there.

```markdown
# Email & Calendar — use the `pa` CLI

- All email, calendar and contacts access goes through the `pa` CLI
  (source: ~/personal-assistant, from github.com/RaggedR/personal-assistant).
- Discover the surface with `pa --help`, `pa mail --help`, `pa cal --help`,
  `pa contacts --help`. Do not guess flags.
- Add `--json` to any command when you need to parse the output. Ids appear in
  every listing, so a listing pipes into a `read`.
- Exit codes: 0 ok, 2 bad args, 3 not authenticated, 4 not found, 5 API error,
  7 confirmation required (nothing happened).

## Hard rule — never send without permission

- **NEVER send an email without explicit, per-message permission in the current
  conversation.** Drafting is always fine.
- `pa mail send` refuses without `--confirm`, exits 7, and prints a preview
  instead. **Never pass `--confirm` unless that specific message has been
  approved.** Do not add it pre-emptively "so it works".
- Correct workflow: `pa mail draft ...` → show them the preview → only then
  `pa mail send --draft-id <id> --confirm`.
- The same gate guards `pa mail trash`, `pa mail discard` and `pa cal delete`.
  Treat exit code 7 as "ask", never as "retry with --confirm".
- `pa cal create/update/delete` only email attendees when `--notify` is passed.
  Outbound notifications need the same permission as sending mail.
```

### Step 4.3 — Hand over

> You're set up. From now on you can just ask me things like:
>
> - "What's on my calendar this week?"
> - "Any unread mail from Alex?"
> - "Draft a reply to that saying I'll have it done by Friday"
>
> I'll draft, you approve, and only then does anything actually get sent.
>
> One thing to expect: Google may make you re-run `pa auth login` after about a
> week, because the app is in "testing" mode. I'll tell you if that happens, and
> there's a permanent fix if it gets annoying — just ask.

→ STOP. Setup is complete.

Only now, if you judge it useful and they seem willing, may you offer Appendix A
(GitHub account and CLI). It is unrelated to `pa` and entirely optional. If in
any doubt, don't — finishing cleanly is better than tacking on fifteen more
minutes of setup they did not ask for.

---
## Appendix A — Optional: GitHub account, CLI and token

**None of this is needed to set up `pa`.** The repository is public, so cloning
it requires no GitHub account, no `gh`, and no token — Stage 1 works on a
completely unauthenticated machine.

Do not walk them through this as part of setup. It is here because a GitHub
account and a working `gh` are genuinely useful for other work with Claude
(filing issues, opening pull requests, private repositories), so it is worth
having written down. Offer it *after* Stage 1 is finished and working, as a
separate thing, and only if they want it:

> Everything's working. Separately — and entirely optionally — do you want me to
> set you up with a GitHub account and command-line access? It's not needed for
> any of this, but it's useful if we end up working on code together. Takes
> about 15 minutes. Happy to skip it.

If they say no, you are done. If they say yes, the same one-step-at-a-time rule
applies throughout.


### A.1 — GitHub account

Skip this entire stage if `gh auth status` showed them logged in.

#### Step A.1.1 — Do they have an account?

> Do you already have a GitHub account? If you're not sure, that means no.

→ STOP.

If yes, skip to A.2.

#### Step A.1.2 — Sign up

> Open this URL:
>
> https://github.com/signup
>
> Enter your email address and click **Continue**.

→ STOP.

#### Step A.1.3 — Password

> Now it will ask for a password. Use something long — a password manager is
> ideal if you have one. Enter it and click **Continue**.

→ STOP.

#### Step A.1.4 — Username

> Next it asks for a username. This is public and hard to change later, so pick
> something you're happy having attached to your name — many people use some
> form of their own name.
>
> Enter it and click **Continue**. If it says the name is taken, try a variation.

→ STOP.

#### Step A.1.5 — Preferences and verification

> It will ask whether you want product emails — answer however you like, then
> click **Continue**.
>
> Then it will show a puzzle or ask you to verify you're human. Complete that,
> then click **Create account**.

→ STOP.

#### Step A.1.6 — Email code

> GitHub has emailed you an 8-digit code. Find that email, type the code into
> the boxes on the page, and you should land on a welcome screen.
>
> If it asks you questions about your experience level or interests, you can
> skip all of that — look for a **Skip personalization** link at the bottom.
>
> What's your GitHub username? I'll need it in a moment.

→ STOP.


### A.2 — Install the GitHub CLI

Skip if `gh --version` already worked.

#### Step A.2.1 — Install it

This is your job, not theirs. Pick the branch matching their OS.

**macOS**, if `brew` exists:

```bash
brew install gh
```

**macOS**, if `brew` does not exist — Homebrew's installer needs their admin
password, which they must type themselves. Tell them:

> I need to install Homebrew first, which is the standard way to install
> command-line tools on a Mac. It needs your Mac login password, so you'll have
> to run this one yourself.
>
> Open the Terminal app and paste in this line, then press Enter:
>
> ```
> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
> ```
>
> It will ask for your password — the characters won't appear as you type, which
> is normal. It takes a few minutes. Tell me when it finishes, and paste the
> last few lines it printed.

→ STOP. The final lines often contain PATH instructions you need to follow.

**Windows**:

```bash
winget install --id GitHub.cli -e
```

**Debian/Ubuntu Linux** — needs `sudo`, so they run it:

```bash
sudo apt update && sudo apt install gh
```

#### Step A.2.2 — Confirm

Run `gh --version` yourself and report the result in one line.

→ STOP.


### A.3 — GitHub personal access token

A token lets `gh` act on their behalf from the command line.

**Note for you:** if they would rather not create a token, `gh auth login` also
offers a browser flow that needs no token at all — choose *GitHub.com* →
*HTTPS* → *Login with a web browser* and read them the one-time code. That is
genuinely simpler and just as valid. Offer it if they hesitate or get stuck.
Otherwise follow the token path below, which is more convenient for scripting later.

#### Step A.3.1 — Open the token page

> Open this URL:
>
> https://github.com/settings/tokens/new
>
> If it asks you to confirm your password or 2FA code first, do that.
>
> You should land on a page headed **New personal access token (classic)**.
> Tell me if you see that, or if you see something different.

→ STOP.

If they landed somewhere else, the menu path is: click your **avatar** in the
top-right corner → **Settings** → scroll to the very bottom of the left-hand
sidebar → **Developer settings** → **Personal access tokens** → **Tokens
(classic)** → **Generate new token** → **Generate new token (classic)**.

Note there are two kinds of token — *Fine-grained* and *classic*. They need
**classic**. If the page says "Fine-grained tokens", they are on the wrong one.

#### Step A.3.2 — Name and expiry

> In the **Note** field at the top, type:
>
> ```
> Claude Code
> ```
>
> Just below it there's an **Expiration** dropdown, probably set to 30 days.
> Change it to **90 days**. (You can pick "No expiration", but a token that
> never expires is a token that can never be forgotten about safely.)
>
> Don't click anything else yet.

→ STOP.

#### Step A.3.3 — Scopes

> Now a long list of checkboxes headed **Select scopes**. Check exactly these
> four:
>
> - **repo** — the first one in the list. Clicking the top-level `repo` box
>   ticks all the boxes indented beneath it. That's correct.
> - **workflow** — just below the repo group.
> - **gist** — further down, on its own.
> - **read:org** — this one is *indented underneath* **admin:org**. Do not tick
>   `admin:org` itself; expand it if needed and tick only `read:org`.
>
> Leave everything else unchecked. Tell me when those four are ticked.

→ STOP.

#### Step A.3.4 — Generate

> Scroll to the very bottom and click the green **Generate token** button.
>
> The next page shows your token — a long string starting with `ghp_`. It is
> shown **once only**; if you navigate away it's gone forever and you'd have to
> make a new one.
>
> Click the copy icon next to it to copy it to your clipboard. **Don't paste it
> here** — I don't need to see it, and chat transcripts get stored.

→ STOP.

#### Step A.3.5 — Give it to `gh`

They must do this in their own terminal so the token never enters the chat.

> Open a terminal window — on a Mac that's the **Terminal** app, on Windows use
> **PowerShell** — and paste in this line, then press Enter:
>
> ```
> gh auth login --with-token
> ```
>
> The cursor will just sit there waiting. Paste your token (Cmd+V or Ctrl+V) and
> press Enter, then press **Ctrl+D**.
>
> If it worked, it prints nothing at all — silence is success here. Tell me when
> you've done it.

→ STOP.

#### Step A.3.6 — Verify

Run this yourself:

```bash
gh auth status
```

It shows the account and scopes but never the token. Report in one line:

> You're logged in to GitHub as `<username>`, with the right permissions.

If it fails, the most likely causes are a partially-copied token or a missed
Ctrl+D. Have them repeat 3.5. If it fails twice, switch to the browser flow
(`gh auth login`, choose *Login with a web browser*).

→ STOP.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `access_blocked`, "app has not completed verification" | Their address is not in Test Users | Step 3.7a/3.7b test-users sub-step |
| `redirect_uri_mismatch` | Client created as "Web application" | Redo 3.8–3.10 choosing **Desktop app** |
| `Token refresh failed` after ~a week | Refresh tokens expire in 7 days for unverified apps in *testing* with sensitive scopes | `pa auth login --force`. Permanent fix: on the consent screen / Audience page click **PUBLISH APP** (no review needed for personal use), or use *Internal* on a Workspace account |
| `Client: ... (MISSING)` in `pa auth status` | Step 3.11 not done | `pa auth setup-client <path to downloaded json>` |
| `insufficient authentication scopes` | A checkbox was left unticked at 3.14 | `pa auth login --force`, tick everything |
| `SERVICE_DISABLED` / "People API has not been used" | An API was enabled on the wrong project | Re-check 3.2, then redo 3.3–3.5 with `pa-cli` selected |
| `pa: command not found` | `~/.local/bin` not on PATH | Step 2.3 |
| `ImportError ... pyexpat` when installing | Broken Homebrew `pipx` | Use `uv` instead (2.2) |
| Contacts `[ok]` but searches return nothing | People API needs a warm-up before first search; `pa` does this automatically, but a brand-new account may genuinely have no "other contacts" yet | Try `pa contacts search` with a name they have definitely emailed |
| Everything worked, then stopped after they changed Google password | Google revokes tokens on password change | `pa auth login --force` |

If you hit something not in this table, say so honestly and suggest they ask
Robin, rather than experimenting inside a console that controls their mailbox.

---

## Reference — what `pa` can do

Read `README.md` in the cloned repo for the full surface. The short version:

```bash
pa mail search 'from:alex is:unread' -n 10
pa mail read <id> --mark-read
pa mail thread <id> --full
pa mail draft --to x@y.com --subject 'S' --body-file notes.md
pa mail send --draft-id <id> --confirm      # only with explicit permission
pa cal list --from today --to +7d
pa cal create --title 'Sync' --start 'tomorrow 10:00' --duration 45
pa cal freebusy --from today --to +3d
pa contacts resolve 'alex'
```

Times accept `now`, `today`, `tomorrow`, weekday names, `+3d` / `-2h` / `+90m`,
`2026-09-01 14:00`, and full ISO 8601. Naive times are local, never UTC.
