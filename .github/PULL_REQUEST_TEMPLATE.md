## Description

<!-- Brief summary of the change and why it's needed. Link any related issues. -->

## Checklist

- [ ] Tests pass: `uv run pytest -m "not live"`
- [ ] Ruff lint clean: `uv run ruff check`
- [ ] Ruff format clean: `uv run ruff format --check`
- [ ] VERSION bumped (patch unless this is a milestone)
- [ ] CHANGELOG.md updated
- [ ] If code change: regression test written (RED before GREEN)
- [ ] If cron/heartbeat change: `traderbot cron setup-heartbeat-tasks --replace` verified
- [ ] If config change: `openclaw config set` used (not direct json edit)
- [ ] Deployed to macpro-linux and verified

## Deployment notes

<!-- Any manual steps needed after deploy? Git pull? Pip install? Restart? -->