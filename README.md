# Daily Facts Bot

Every morning, an AI agent finds the single most surprising thing that happened on today's date in history. It drafts 3 tweet options. You pick one and post.

Not "on this day in 1969, Apollo 11 landed." Everyone knows that.

More like: "17 seconds of fuel. That's what Apollo 11 had left when it touched down. Armstrong flew past boulders for 4 minutes. Houston watched. They said nothing."

---

## How It Works

Every day at 8am:

1. The agent searches across 8 domains: geopolitics, science, sports, art, business, geography, law, medicine
2. It filters for facts that are surprising, specific, human, and standalone
3. It drafts 3 tweet options with different angles: The Buried Detail, The Number, The Human Decision
4. A brief lands in your Telegram with all 3 options
5. You tap the best one, copy, post. 30 seconds.

The agent rotates domains so the feed never becomes all-history or all-science.

---

## Example Brief

```
DAILY FACTS BRIEF | Monday, May 19

Today's fact: Apollo guidance computer threw 1,202 errors during moon landing
Domain: science and discovery
Year: 1969

TWEET OPTIONS

[A] The Buried Detail

1,202. That's how many software alarms the Apollo 11 computer threw during descent.
Engineers had never seen most of them. They had 90 seconds to decide: abort or land.
They landed.
(191 chars)

[B] The Number

The Apollo 11 guidance computer ran on 4KB of RAM. Less than a modern calculator.
It still landed two humans on the moon while throwing 1,202 error codes in real time.
(172 chars)

[C] The Human Decision

July 20, 1969. The Apollo 11 computer kept alarming. Nobody knew why. Engineer Jack
Garman had one rule: if the computer restarts and keeps flying, let it go. It restarted.
He let it go.
(189 chars)
```

---

## Setup

**1. Create a GitHub repo and push this code**

```bash
cd daily-facts-bot
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/daily-facts-bot.git
git push -u origin main
```

**2. Add GitHub secrets** (repo Settings → Secrets → Actions):

| Secret | Where to get it |
|--------|----------------|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `BRAVE_API_KEY` | api.search.brave.com |
| `TELEGRAM_BOT_TOKEN` | @BotFather on Telegram |
| `TELEGRAM_CHAT_ID` | Send your bot a message, then call `api.telegram.org/bot{TOKEN}/getUpdates` |

**3. Update config.yaml** with your X handle.

**4. The workflow starts automatically** at 8am CDT every day.

---

## Customising

- **Change posting time:** Edit the cron in `.github/workflows/daily-facts.yml`
- **Change domains:** Edit `config.yaml`
- **Change tweet style:** Edit `.github/prompts/facts-generator.md` Step 4
- **Skip a day manually:** The agent writes `SKIP` if it cannot find a fact that passes the quality bar. No tweet is sent.

---

## Stack

- **GitHub Actions** — runs on schedule, no server needed
- **Anthropic Claude Sonnet** — picks the angle and writes the tweet
- **Brave Search** — finds historical events for today's date
- **Telegram Bot API** — delivers the brief to your phone
