Telegram Signal Forwarding Bot
==============================

This repository contains a Python script that listens to multiple Telegram
channels for new trading signals, extracts the key parameters (instrument,
entry price, take‑profit levels, stop loss, etc.), and forwards them to one or
more destination channels in a clean, standardized format.

The bot is built using the `Telethon` library and is designed to run
continuously on a free hosting service such as Render, Railway or
PythonAnywhere.  It operates as a user client (not a bot token), so it can
read messages from channels that do not explicitly mention the bot.  You must
authenticate it once using your Telegram account; thereafter it will reuse the
saved session.

Key Features
------------

* **Multi‑channel listener:** Monitor several source channels for new
  messages.
* **Signal detection:** Automatically identify messages that contain trading
  signals by looking for an instrument, trade direction, entry price, take
  profits and stop loss.  Non‑signal messages such as updates, polls, or
  announcements are ignored.
* **Flexible parsing:** Support multiple message styles from different signal
  providers (e.g. formats used by GOLD EXCLUSIVE VIP, Forex.RR Premium and
  Lingrid private signals).  You can refine the parsing logic in
  `parse_signal()` for additional providers.
* **Customizable forwarding:** Send the formatted signal to any number of
  destination channels.  Destination channels can be specified by numeric ID
  (prefixed with `-` for supergroups) or by username (prefixed with `@`).

Setup
-----

1. **Clone the repository** to your hosting platform or local machine.
2. **Install dependencies**.  A single dependency is required:

   ```bash
   pip install -r requirements.txt
   ```

3. **Create a Telegram application** at
   https://my.telegram.org/apps and note down your `api_id` and `api_hash`.

4. **Define environment variables**.  The bot reads its configuration from
   environment variables.  At a minimum you need to set:

   ```bash
   export TG_API_ID=29278288
   export TG_API_HASH=8baff9421321d1ef6f14b0511209fbe2
   export TG_SOURCE_CHANNELS=hfjfdjjdd,GOLD EXCLUSIVE VIP,Forex.RR - Premium,Lingrid private signals
   export TG_DEST_CHANNELS=-1467736193,-2123816390,-1286609636,@sjkalalsk
   ```

   You can also override the session file name with `TG_SESSION` if you wish.

5. **Run the bot**:

   ```bash
   python telegram_signal_bot.py
   ```

   On the first run you will be prompted for your phone number and a
   confirmation code sent to your Telegram account.  After successful
   authentication the session will be saved to disk and reused on subsequent
   runs.

Deployment
----------

To host the bot for free and ensure it runs 24/7, you can deploy it to a
platform like **Render**, **Railway** or **PythonAnywhere**.  Here is an
example of deploying as a background worker on Render:

1. Create a new **Web Service** or **Background Worker** on Render.
2. Connect your GitHub repository containing this code.
3. Set the **Start Command** to:

   ```bash
   python telegram_signal_bot.py
   ```

4. Add the environment variables (`TG_API_ID`, `TG_API_HASH`, `TG_SOURCE_CHANNELS`,
   `TG_DEST_CHANNELS`, etc.) in the **Environment** section.

Once deployed, the bot will start automatically and keep running even when
your local machine is off.  You can view logs in the hosting dashboard to
monitor activity and troubleshoot issues.

Customization
-------------

If you need to support additional signal providers or refine the detection
criteria, modify the `parse_signal()` and `is_signal_message()` functions in
`telegram_signal_bot.py`.  These functions use regular expressions and simple
heuristics to decide whether a message is a signal and to extract the
relevant fields.

Contributing
------------

Pull requests are welcome!  If you encounter edge cases with specific signal
formats or have suggestions to improve performance or reliability, feel free
to open an issue or submit a patch.
