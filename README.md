# 🎮 CS2 & Dota 2 Telegram Match Tracker

A Telegram bot for tracking professional **Counter-Strike 2** and **Dota 2** matches.

The bot allows users to follow teams and tournaments, receive match notifications, view upcoming matches and results, and get daily esports summaries directly in Telegram.

> 🚧 The project is actively under development.

## ✨ Features

### 🎯 Team Tracking

- Follow professional CS2 and Dota 2 teams
- View upcoming matches
- View recent results
- View team statistics
- Manage tracked teams through Telegram

### 🔔 Match Notifications

The bot is designed to provide notifications for:

- ⏰ Upcoming matches
- 🔴 Match start
- 🏆 Match completion
- 📊 Match results and scores

Users will be able to customize which notifications they receive.

### 📅 Matches

- Today's matches
- Upcoming matches
- Next match for a tracked team
- Completed match results

### 🏆 Tournament Tracking

Users can:

- Browse tournaments
- Follow specific tournaments
- Hide tournaments they are not interested in
- Restore hidden tournaments
- View tournament information
- View tournament standings and stages

### 📊 Team Statistics

For tracked teams, the bot can provide:

- Recent matches
- Wins and losses
- Upcoming matches
- Current tournament information
- Match results

### 📝 Daily Summary

The bot can generate a daily esports summary containing:

- CS2 results
- Dota 2 results
- Results of tracked teams
- Important matches and events

---

## 🎮 Supported Games

| Game | Support |
|------|---------|
| Counter-Strike 2 | ✅ |
| Dota 2 | ✅ |

---

## 🏗️ Architecture

The project uses a shared match-processing pipeline:

```text
             Data Providers
                  │
           ┌──────┴──────┐
           │             │
          CS2          Dota 2
           │             │
           └──────┬──────┘
                  │
            Match Tracker
                  │
            Tracked Teams
                  │
             Match Event
                  │
        Notification Service
                  │
               Telegram
