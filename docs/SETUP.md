# Setup

`pa` talks to Google APIs on your behalf. Google requires that the *application*
identify itself with an OAuth client, and that *you* consent to it accessing
your data. Those are two separate steps:

1. **Create an OAuth client** (once per machine or per person) — this produces a
   small JSON file. Because it identifies an application rather than a user, it
   is not shipped in this repository and you must create your own.
2. **Log in** — a browser window where you grant access. This produces a refresh
   token stored locally at `~/.config/pa/accounts/default/token.json`.

Budget about five minutes for step 1. You only ever do it once.

---

## Already using the Gmail/Calendar MCP servers?

Skip everything below. `pa` reads `~/.gmail-mcp` and `~/.calendar-mcp` as a
read-only fallback, so mail and calendar work immediately:

```bash
pa auth status
```

Come back here when you want Contacts, or a second account.

---

## Step 1 — Create a Google Cloud OAuth client

### 1.1 Create a project

Go to <https://console.cloud.google.com/projectcreate>, name it anything
(`pa-cli` is fine), and create it. Make sure it is the selected project in the
picker at the top of the page before continuing.

### 1.2 Enable the APIs

Enable each of these for your project (the Contacts one is optional — skip it
if you do not want `pa contacts`):

- [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
- [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com)
- [People API](https://console.cloud.google.com/apis/library/people.googleapis.com)

Click **Enable** on each page.

### 1.3 Configure the consent screen

Go to **APIs & Services → OAuth consent screen**.

- **User type**: *External* unless you are inside a Google Workspace
  organisation and only need your own domain, in which case *Internal* is
  simpler because it skips the test-user step.
- **App name**: anything, e.g. `pa`.
- **User support email** and **Developer contact**: your own address.
- **Scopes**: you may leave this empty. `pa` requests its scopes at login time.
- **Test users**: if you chose *External*, add your own Google address here.
  Without this, login fails with `access_blocked`.

You do **not** need to submit the app for verification. It stays in "testing"
mode, which is fine for personal use. Google expires refresh tokens for unverified
apps after 7 days *only* for apps in testing with sensitive scopes — if you find
yourself re-running `pa auth login` weekly, either publish the app (no review is
required to move an app to production for your own use) or use *Internal* type.

### 1.4 Create the client

Go to **APIs & Services → Credentials → Create credentials → OAuth client ID**.

- **Application type**: **Desktop app** — this matters. `pa` uses the installed-app
  loopback flow; a "Web application" client will not work.
- **Name**: anything.

Click **Create**, then **Download JSON**. You get a file called something like
`client_secret_1234-abcd.apps.googleusercontent.com.json`.

### 1.5 Install it

```bash
pa auth setup-client ~/Downloads/client_secret_1234-abcd.apps.googleusercontent.com.json
```

This validates the file and copies it to `~/.config/pa/client.json` with mode
`0600`. You can delete the download afterwards.

---

## Step 2 — Log in

```bash
pa auth login
```

A browser opens. Choose your Google account and grant access. You will see an
"unverified app" warning — that is expected for your own client; click
**Advanced → Go to pa (unsafe)**.

Verify:

```bash
pa auth status
```

```
Account:  default
Home:     /Users/you/.config/pa
Timezone: Australia/Melbourne
Client:   /Users/you/.config/pa/client.json (present)

  [ok  ] gmail     pa store (/Users/you/.config/pa/accounts/default/token.json)  you@gmail.com
  [ok  ] calendar  pa store (/Users/you/.config/pa/accounts/default/token.json)
  [ok  ] contacts  pa store (/Users/you/.config/pa/accounts/default/token.json)
```

Then try it:

```bash
pa mail search 'is:unread' -n 5
pa cal list --from today --to +7d
```

---

## Scopes requested, and why

| Scope | Needed for |
|---|---|
| `gmail.modify` | Read messages, manage labels, create drafts, send, move to Trash |
| `gmail.settings.basic` | Read filters and basic settings |
| `calendar` | Full read/write on your calendars |
| `contacts.readonly` | Read saved contacts |
| `contacts.other.readonly` | Read "other contacts" — people you have emailed but not saved |
| `directory.readonly` | Read your Workspace directory, if you are in one |

Deliberately **not** requested: `https://mail.google.com/`, which would permit
permanent, unrecoverable deletion of mail. `gmail.modify` cannot do that, so
the worst `pa` can do to a message is move it to Trash.

To grant only some services:

```bash
pa auth login --service gmail --service calendar
```

---

## Multiple accounts

Accounts are keyed by a local nickname:

```bash
pa --account work auth login
pa --account work mail search 'is:unread'
```

Each gets its own directory under `~/.config/pa/accounts/`. To use a different
OAuth client for one account, put a `client.json` in that account's directory;
otherwise the shared `~/.config/pa/client.json` is used.

Set a persistent default:

```bash
export PA_ACCOUNT=work
```

---

## Troubleshooting

**`access_blocked` / "app has not completed verification"**
Add your Google address as a Test User on the OAuth consent screen (step 1.3).

**`redirect_uri_mismatch`**
Your client is the wrong type. Create a new one of type **Desktop app** (step 1.4).

**`Token refresh failed` after about a week**
Refresh tokens for apps in *testing* with sensitive scopes expire after 7 days.
Either publish the app in the consent screen, or switch to *Internal* if you are
in a Workspace org. Then `pa auth login --force`.

**`insufficient authentication scopes` after upgrading `pa`**
A new version asked for a scope you have not granted. `pa auth login --force`.

**`Client: ... (MISSING)` in `pa auth status`**
Step 1.5 was not completed. Run `pa auth setup-client <path>`.

**Where is everything?**

```
~/.config/pa/client.json                    shared OAuth client
~/.config/pa/config.json                    default account, timezone override
~/.config/pa/accounts/<name>/token.json     refresh token (0600)
```

Nothing else is written, and nothing is ever written to `~/.gmail-mcp` or
`~/.calendar-mcp`.
