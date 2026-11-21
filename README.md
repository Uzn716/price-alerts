# PC Price Alerts

A Discord notifier for **price errors on gaming PC parts**. It runs for free on
GitHub's servers every 10 minutes, so your own computer never has to stay on.

| Store | How it's checked | Cost |
|---|---|---|
| **Amazon** | Keepa API (price history + deal scanner) | Paid Keepa plan |
| **Best Buy** | Best Buy's official Products API | Free key |
| **Newegg, Micro Center, B&H, Walmart, and others** | Slickdeals deal feeds, where shoppers post deals as they find them | Free, no key |

Every source is optional. With **no keys at all**, the bot still watches the
Slickdeals feeds, so you can start free and add stores later.

---

## Setup (about 15 minutes)

### 1. Create a Discord webhook
A webhook is a private link that lets the bot post into one channel.

1. In Discord, pick a server where you have admin rights. Your own server works fine;
   to make one, click **+** in the server list and choose **Create My Own**.
2. Open **Server Settings → Integrations → Webhooks → New Webhook**.
3. Pick the channel for alerts (e.g. `#price-errors`) and click **Copy Webhook URL**.
4. Keep that URL private. Anyone who has it can post in your channel.

### 2. Put the code on GitHub
1. Make a free account at <https://github.com>.
2. Click **+ → New repository**. Name it something like `pc-price-alerts`, choose
   **Public** (which keeps GitHub Actions free and unlimited), and click
   **Create repository**.
3. On the new empty repo page, click **uploading an existing file**.
4. Unzip `pc-price-alerts.zip` on your computer, open the folder, select
   **everything inside it** (including the `.github` folder), drag it onto the
   page, and click **Commit changes**.
   * **Mac:** `.github` is hidden by default. Press **Cmd + Shift + .** in
     Finder to show it.
   * **If `.github` didn't upload:** click **Add file → Create new file**, type
     `.github/workflows/price-check.yml` as the name, paste in the contents of
     that file from the zip, and commit.

> Your code and watchlist are public, but your keys are **not**. They go in
> GitHub Secrets (next step), which stay hidden even in a public repo. Never put
> keys or the webhook URL in `config.yaml`.

### 3. Add your secrets
In your repo, go to **Settings → Secrets and variables → Actions → New repository secret**
and add each of these:

| Name | Value | Required? |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | The webhook URL from step 1 | **Yes** |
| `KEEPA_API_KEY` | Your Keepa API key (see below) | Only for Amazon |
| `BESTBUY_API_KEY` | Your Best Buy API key (see below) | Only for Best Buy |

### 4. Turn it on and send a test
1. Open the **Actions** tab. If GitHub asks, click **I understand my workflows, go ahead and enable them**.
2. Click **Price check** on the left, then **Run workflow**. Set *mode* to
   **test-discord**, then click **Run workflow**.
3. Within about a minute you should get a test message in Discord that lists
   which stores are connected.

You're done. From now on GitHub runs the check every ~10 minutes on its own.
The very first run quietly remembers what's already in the Slickdeals feeds,
so you won't get flooded with old posts.

---

## Getting the optional API keys

### Keepa (Amazon)
Keepa tracks Amazon's price history, which is what lets the bot tell a true
error from an ordinary sale. Amazon blocks scrapers, so this is the reliable route.

1. Create an account at <https://keepa.com>.
2. Subscribe. The API is paid: the regular Keepa subscription includes a small
   API allowance (about 1 token per minute), and dedicated API plans cost more
   for higher allowances. Check Keepa's site for current prices.
3. Your key is on the **API** / **Data Access** page of your Keepa account.

**What the tokens buy:** each watched Amazon listing costs 1 token per check,
and each deal scan (which sweeps Amazon Electronics for big price drops) costs
5. The bot checks your token balance first and only spends what you have. If you
watch more listings than your tokens cover, it rotates through them. With the
smallest allowance, you get roughly one deal scan every 30 minutes plus a few
watched listings per run.

### Best Buy
1. Go to <https://developer.bestbuy.com> and click **Get API Key**.
2. Best Buy has said it won't issue keys to free email addresses
   (Gmail, Yahoo, and so on), so you may need another address, such as one on
   your own domain. The key is free, and the bot uses a tiny fraction of its
   daily limit.

---

## Customizing (`config.yaml`)

To change settings, open `config.yaml` in your repo on GitHub, click the
**pencil icon**, edit, and click **Commit changes**. The next run picks up the
change. Things you'll most likely want to change:

* **`alert_below`** on each part: the price that would make you buy right away.
  The starting numbers are examples set well under launch prices.
* **`min_drop_percent`**: how far below normal counts as an error (default 35%).
* **Adding a part:** copy an existing entry and change `name` and `match`.
  Every word in `match` must appear in the product title. Use `exclude` to rule
  out near-misses (the RTX 5070 entry excludes `ti`).
* **Watching an exact Amazon listing:** add its link under `amazon:` (needs Keepa).
* **Getting pinged:** set `mention: "@here"`, or ping only yourself. Turn on
  Discord **Settings → Advanced → Developer Mode**, right-click your name,
  choose **Copy User ID**, then set `mention: "<@YOUR_ID>"`.
* **More Slickdeals alerts:** set `alert_all_matches: true` on a feed to hear
  about *every* new deal on your parts, not only probable errors.

## How it decides something is a price error

A listing has to match one of your parts (or, for untracked PC parts, the
`general_keywords` with a stricter 50% bar), cost at least `min_price`, and then
meet at least one of these:

* **Far below its normal price.** For Amazon, "normal" is the lower of Keepa's
  30-day and 90-day averages. For Best Buy, it's the lower of Best Buy's
  "regular price" and the bot's own record of what that item usually sells for.
  Using the lower number avoids false alarms from inflated "was" prices.
* **Under your `alert_below` price.**
* **Called a price error.** A Slickdeals post that says "price error",
  "price mistake", "glitch", or similar.

Each listing alerts once. It alerts again only if the price drops another 5%,
or after `realert_after_hours`.

## Troubleshooting

* **Where are the logs?** Open **Actions → Price check** and click any run.
  The **Run** step lists each store, how many listings it checked, and any alerts.
* **"skipped (not enabled or no API key)":** that store's secret is missing or
  misspelled. Secret names must match exactly.
* **A store keeps failing:** after 3 failures in a row, you get one warning in
  Discord, and the other stores keep working. A common cause is a site
  blocking GitHub's servers. Slickdeals could do that.
* **Runs start late or skip a slot:** that's normal for GitHub's free scheduler,
  especially near the top of the hour.
* **Pausing the bot:** open **Actions → Price check → ⋯ → Disable workflow**.
* **Seeing what it would alert on without posting:** run the workflow manually
  with mode **dry-run** and read the log.
* **It stops after a couple of months:** GitHub pauses scheduled jobs in repos
  with 60 days of no activity. The bot prevents this with a tiny automatic commit
  once a month. If it ever does pause, click **Enable workflow** on the Actions tab.

## Good to know

* Retailers often cancel orders placed at error prices. Treat alerts as a
  chance at a deal, not a guarantee.
* Errors can disappear within minutes, and with checks every ~10 minutes a few
  will slip past.
* Amazon alerts default to items **sold by Amazon itself**. Errors there are
  the most likely to be honored, and you avoid fake third-party "deals". Set
  `keepa.price_type: new` to include all sellers.

## Running it on your own computer (optional)

```bash
pip install -r requirements.txt
export DISCORD_WEBHOOK_URL="..."   # plus KEEPA_API_KEY / BESTBUY_API_KEY if you have them
python -m pricebot --dry-run       # print alerts instead of posting
python -m pricebot --test-discord  # send a test message
python -m pytest                   # run the tests (pip install pytest first)
```
