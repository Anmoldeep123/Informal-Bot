# Discord Informal Signup Bot

An automated Discord bot that manages hourly informal event signups.

## Features
- Opens signups automatically at XX:00 IST every hour.
- Closes signups automatically at XX:10 IST.
- Interactive Join and Leave buttons.
- Main roster (10 slots) and backup roster (2 slots).
- Slash commands to enable (`/startinformalbot`) or disable (`/stopinformalbot`) the schedule (owner only).

## Hosting on FadeHost

1. Upload these files to your GitHub Repository.
2. Connect your GitHub repository to your FadeHost Panel.
3. Set your environment variable in FadeHost settings:
   - `DISCORD_TOKEN`: Your actual Discord Bot Token.
4. Launch/Start the bot worker.
