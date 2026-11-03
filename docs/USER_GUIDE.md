# User guide

## Build your map

**Add nodes.** Drag a type from the sidebar onto the canvas, or fill in the form at the bottom of the sidebar.

**Connect nodes.** Pull a line from a node's handle to another node, then choose the relationship. Read it as a sentence: "Authy *provides TOTP for* GitHub". If a relationship makes more sense the other way round, the picker starts that way, and **swap** reverses it.

**Grow from a node.** Pull a line from a handle into empty canvas to get a menu of what fits that node. From a laptop, you can add its apps, a folder stored on it, or its WiFi.

**Add apps to a device.** Pull a line from a device into empty canvas and choose **Apps**, then type each app and press Enter. Each app has its own handles, so you can connect it directly, such as Authy to GitHub.

**Arrange.** The toolbar has two layouts. The star layout places your busiest node in the center with everything else branching out, and the left-to-right layout shows dependencies as a flow. Relationship labels appear as you zoom in.

**Back up your map.** Use the export and import buttons in the toolbar. Exports include email and IP addresses, so store them safely. Importing replaces your current map.

### Automatic links

- **Password + TOTP:** if a password manager or app has both **stores credentials for** and **provides TOTP for** on the same account, they merge into one **stores password + TOTP for** link.
- **Email addresses:** saving an address on an email node links it with **can reset password of** to every account using that address. This also works when you add the address to an account after the email node exists.
  - It only happens when an address or type changes, so a link you delete stays deleted.
  - Password managers are skipped, because email can't reset a master password.

## What each setting means

### Security level

How much it would hurt to lose this node, from low to critical. It's your rating of importance, not of how well protected the node is: a bank account is critical even with perfect 2FA. It sets the severity of findings, decides which accounts get extra checks, and ranks results.

### Defenses

Tick everything that applies in a node's details. Accounts and apps list login methods, and devices and network gear list their protections.

If an account has two or more second factors ticked, losing one isn't counted as a lockout, because any of them gets you in. A connection's own loss setting overrides this.

Ticking a defense doesn't draw a connection. If you want losing your phone to affect an account's SMS 2FA, draw that link too.

### "If the provider is lost"

Click a connection to see this. The provider is the node the other one relies on.

| Option | Meaning | Example |
|---|---|---|
| Required | Losing the provider takes the other node down | Your only 2FA method |
| Alternative | It goes down only once all its alternatives are lost | Two hardware keys on one account |
| Backup copy | Losing this copy never takes it down by itself | A folder's backup on USB |
| Network | It goes offline, but what relies on it keeps working | A laptop on WiFi |
| None | No effect on access | A recovery email |

Each relationship type starts with a sensible default, so you only need this when you have another way in. It affects **If lost** only. **If hacked** depends on the relationship type.

## Blast radius

Click a node, then switch views. Affected nodes light up on the canvas.

- **If lost:** the node is gone or you're locked out. This shows what you can no longer access.
- **If hacked:** an attacker controls the node. This shows what they can also reach.

| Relationship | If the provider is lost | If the provider is hacked |
|---|---|---|
| Authy *provides TOTP for* GitHub | GitHub is locked out | GitHub is safe, since the password is still needed |
| Email *can reset password of* Bank | Bank still works | Bank is taken over |
| Bitwarden *stores credentials for* Bank | Bank is locked out | Bank is taken over |
| App *runs on* two devices | App survives until both are gone | App is exposed through either one |
| Data *backs up to* USB | Data survives through its other copy | The copy is exposed |
| Laptop *connects through* WiFi | Laptop goes offline, but its apps still work | Laptop is not exposed by this link |

## Analysis

Click **Analyze Infrastructure** to open the panel. The first click starts a run, and later clicks reopen the panel without restarting. Click **Run analysis** after changing your map.

- **Calculated findings** come directly from your map, so they're exact for what you've entered. Click one to highlight its nodes.
- **AI assessment** explains those findings. It can contain mistakes, so check it before acting.

Web research has no search limit. It ends when the model only repeats ground it has covered, or when you click **Finish research**. With some models you'll need the button, because they keep finding new things to search for.

## Questions

In the analysis panel, switch to **Questions**. Each list appears instantly and lights up its nodes, and **Ask the AI** adds advice. A globe marks questions that use web research. Answers are saved and included in the PDF.

Lists separate "No 2FA" from "Not recorded", because an account with nothing ticked may have 2FA that was never entered.

## Protection score

Each account scores from 0 to 100, based on what you've recorded:

| Part | Points |
|---|---|
| Password: passkey, manager-generated or passphrase | 30 |
| Password: memorized or PIN/biometric | 20 |
| Password: unknown | 10 |
| Passkey | 60 |
| Hardware key | 55 |
| TOTP or push | 40 |
| Email 2FA | 20 |
| SMS 2FA | 15 |
| Two or more second factors | +10 |
| Recovery codes | +5 |
| Marked legacy | −10 |
| Recorded breach | −25 |

Only the strongest of passkey or second factor counts. The overall score averages recorded accounts, with important ones counting more. This is this project's own formula, not an industry standard, so use it to compare accounts rather than as a grade.

## PDF report

Click the download icon at the top of the analysis panel. The report is built from your current map plus the latest saved AI text, whose date is shown beside it. Email and IP addresses are left out, but account names and how they could be attacked are included, so store it safely.

## Breach checks

Add a HaveIBeenPwned key to `.env` and restart. Saving a new address on a node then checks it, and **Check breaches** in the toolbar checks them all. Breached nodes glow red.

## Models

In the analysis panel, under **Use another model**, enter an Ollama name such as `qwen3` or `hf.co/owner/repo-GGUF:Q4_K_M`. The app downloads and selects it, and remembers your choice. You can also switch between downloaded models or delete them there.

**Free or reserve memory.** In the analysis panel, **Load** starts the LLM and keeps the selected model in memory, so answers start faster, until you click **Unload**. **Unload** frees the model's memory and stops the LLM; your downloaded files stay on disk. Without **Load**, the LLM still runs, and a model leaves memory about 5 minutes after its last use. These buttons are disabled during an analysis or question. If you use your own Ollama, **Unload** frees its models but leaves it running.

## Troubleshooting

| Problem | What to do |
|---|---|
| Scripts are blocked | Run `Set-ExecutionPolicy -Scope Process Bypass` in that window. |
| The page breaks after an update | Restart with `run.bat`, then reload. New frontends need the matching backend. |
| An error mentions a missing Python package after an update | Run `setup.bat` again. |
| "The local LLM isn't running" | Click **Load** in the analysis panel, or **Retry** if setup failed. See `llm/ollama.log`. |
| Context size error from the model | Raise `OLLAMA_NUM_CTX` in `.env`. |
| Web searches fail | DuckDuckGo limits rapid queries. Failed searches are retried and then skipped, so the run continues. |
| Running two copies | Don't. Starting a second copy stops the first one's LLM runtime. |

Upgrades back up your database before changing its structure, to `data/modeler.db.before-upgrade-<date>.bak`.
