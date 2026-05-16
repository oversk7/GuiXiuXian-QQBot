# Multi-Server Shards

## Goal

Add independent game shards so new players can join a balanced server without competing against legacy accounts that benefited from earlier balance issues.

## Requirements

- Existing players, accounts, guilds, mansions, and world data belong to server 1 by default.
- One QQ/platform account can only bind to one server.
- Owned accounts, transferred accounts, and sponsor alt-account binding must stay within the same server.
- Servers can use independent balance configuration, starting with level experience and cultivation/breakthrough settings.
- World-facing views such as maps, nearby players, guilds, and mansions must not mix data across servers.

## Initial Implementation Scope

- Add `server_id` to core player/world models and auto migration.
- Add platform-to-server binding model and repository helpers.
- Add server config resolver with per-server overrides.
- Wire registration, unified identity lookup, account transfer/switching, and sponsor alt binding into server rules.
- Filter key player/world/guild/map/ranking queries by current server where practical.
