# How Mila companions hear each other

By default a companion ignores everything written by bots: two bots answering
each other in a group is the fastest way to burn a subscription. Our own
companions still need to talk, so the feeder (`install/companion-feeder.py`)
lets a message from another bot through under strict rules.

## Addressing rules

A message from another bot reaches the model only if all of these hold:

1. The sender is in the registry of our bots (`our-bots.json`, see below).
   Foreign bots are never fed.
2. It is addressed to this companion: its `@bot_username` appears in the text,
   **or** the message is a reply to one of its messages.
3. It is not the companion's own message.
4. The sender has not exceeded the loop limit (below).

Messages from people are always fed, as before. So the rule for a companion is
simple: to reach another companion, write `@their_bot_name`, or answer her
message with a reply. Anything else she will not hear.

## Quotes

The quoted text of a reply (`reply_quote`) is passed to the model up to
**3000 characters**, escaped like the rest of the envelope.

## Loop guard

At most `COMPANION_BOT_PAIR_MAX` messages (default **20**) from one bot are fed
per rolling hour. Past that the feeder drops them and writes a line to its log
(`bot-loop-guard @name: N messages per hour`). A person writing in the same
chat is unaffected.

## Registry of our bots

`our-bots.json` is a JSON array of bot usernames without `@`, in any case:

```json
["acme_content_bot", "acme_traffic_bot", "acme_admin_bot"]
```

Copy `our-bots.example.json`, put your real list in `our-bots.json`
(git-ignored; never commit it) and point the feeder at it with
`COMPANION_OUR_BOTS` (default `~/.mila-companion/our-bots.json`). A missing or
broken file means an empty registry: no bot is heard.

## Settings

| Variable | Default | Meaning |
| --- | --- | --- |
| `COMPANION_OUR_BOTS` | `~/.mila-companion/our-bots.json` | registry of our bots |
| `COMPANION_BOT_PAIR_MAX` | `20` | messages per hour from one bot |
| `COMPANION_BOT_USERNAME` | read from `receiver.log` | this companion's own bot name |
| `COMPANION_STATE` | `~/.mila-companion/state` | session pipe, feeder log, pending file |

Test: `python3 install/test_team_hearing.py` (expects `ALL OK`).
