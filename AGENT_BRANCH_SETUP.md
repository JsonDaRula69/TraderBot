# Agent Work Branch Setup

## Prerequisites

### 1. Install GitHub CLI
```bash
# macOS
brew install gh

# Or see: https://github.com/cli/cli#installation
```

### 2. Install OpenCode Desktop (Beta)
Download from: **https://opencode.ai/download**

### 3. Install oh-my-openagent
```bash
npm install -g oh-my-openagent@latest
```

### 4. Install cortexkit/opencode-magic-context
```bash
npm install -g @cortexkit/opencode-magic-context
```

### 5. Authenticate with GitHub
```bash
gh auth login
# Select github.com, SSH, and appropriate credentials
```

## Repository
`https://github.com/JsonDaRula69/TraderBot.git`

## Branch Protection (IMPORTANT)
- **main**: Requires 1 approval via Pull Request to merge
- All work must go through a PR before merging to main

## Workflow
1. Clone the repo (or pull latest if already cloned)
2. Create a new branch named `feature/work-branch` (or a descriptive name for your task)
3. Switch to that branch
4. Make your changes there
5. Commit and push your changes
6. Create a Pull Request from your branch to `main`
7. Wait for approval (or approve yourself if you're the owner)
8. Merge the PR

## Credentials
- GitHub account: `JsonDaRula69`
- Authentication: Use `gh auth` or SSH key

## Quick Start
```bash
# Clone (if first time)
git clone https://github.com/JsonDaRula69/TraderBot.git
cd TraderBot

# Or pull latest if already cloned
git checkout main
git pull origin main

# Create YOUR personal dev branch (use your username/agent name)
git checkout -b dev/your-username

# Make changes, commit, push
git add .
git commit -m "feat: description"
git push -u origin dev/your-username
```

Then create a Pull Request from `dev/your-username` to `main` on GitHub.