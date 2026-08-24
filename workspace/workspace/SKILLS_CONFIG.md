# Skills Configuration

This file manages the skills available to pyclaw.

## Skill Structure
Each skill should be placed in: `skills/{skill-name}/SKILL.md`
The SKILL.md file should contain:
- Skill name and description
- Commands/triggers
- Implementation details
- Examples of usage

## Available Skills
Below is the list of configured skills:

### Core Skills (Built-in)
1. **File Management**
   - Path: `skills/file-management/SKILL.md`
   - Status: Enabled
   - Description: Read, write, edit files and directories

2. **Web Operations**
   - Path: `skills/web-operations/SKILL.md`
   - Status: Enabled
   - Description: Search the web and fetch web pages

3. **System Commands**
   - Path: `skills/system-commands/SKILL.md`
   - Status: Enabled
   - Description: Execute shell commands

4. **Communication**
   - Path: `skills/communication/SKILL.md`
   - Status: Enabled
   - Description: Send messages and communicate

5. **Task Management**
   - Path: `skills/task-management/SKILL.md`
   - Status: Enabled
   - Description: Spawn subagents and schedule tasks

### Custom Skills

1. **Notes Manager**
   - Path: `skills/notes-manager/SKILL.md`
   - Status: Enabled
   - Description: Manage notes and journal entries in the workspace
   - Created: 2026-04-16

## Skill Management

### Enabling/Disabling Skills
To disable a skill, change its status to "Disabled" below.
To enable a skill, change its status to "Enabled".

### Adding New Skills
1. Create a directory: `skills/{skill-name}/`
2. Create `SKILL.md` file with skill documentation
3. Add the skill to this configuration file
4. Update the agent's instructions if needed

## Skill Loading Order
Skills are loaded in the order listed above.
Core skills are loaded first, then custom skills.