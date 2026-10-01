# MongoDB Atlas + Render setup

Add these Render environment variables:

- `MONGODB_URI`: the Atlas driver URI. Replace `<password>` with the database user's password; URL-encode special characters in the password.
- `MONGODB_DB_NAME`: `book_sharing_bot`

The app uses MongoDB collections `files`, `admins`, `settings`, `pending_deletions`, `users`, and `user_profiles`. Existing environment variables such as `TG_BOT_TOKEN`, `CHANNEL_ID`, `OWNER_ID`, `WEBHOOK_URL`, and `DEFAULT_ADMINS` remain configured in Render.

After adding the variables, deploy the updated source. Check the Render logs for `Bot ... initialized` and `Indexed files: ...`. MongoDB connectivity is verified during app startup; a bad URI or network rule will stop startup and appear in logs.

Important: Telegram Bot API cannot scan historical channel messages. This archive did not include an existing local `files_index.json`, so MongoDB will begin indexing channel posts received after this version is deployed. To bring older books into `/files`, perform a one-time index migration/import from a saved prior index, or re-post/forward the supported PDF/EPUB items into the configured DB channel once.
