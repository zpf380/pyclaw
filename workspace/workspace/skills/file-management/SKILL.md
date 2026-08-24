# File Management Skill

## Description
This skill provides capabilities for managing files and directories in the workspace.

## Commands/Triggers
- "Read file [path]"
- "Write to file [path]"
- "Edit file [path]"
- "List directory [path]"
- "Create directory [path]"
- "Delete file [path]" (use with caution)

## Implementation
Uses the following tools:
- `read_file(path)` - Read file contents
- `write_file(path, content)` - Write to file
- `edit_file(path, old_text, new_text)` - Edit file
- `list_dir(path)` - List directory contents
- `exec(command)` - For directory operations

## Examples

### Reading a file
```
User: Read the configuration file
Assistant: I'll read the configuration file for you.
```

### Writing to a file
```
User: Save this note to notes.txt
Assistant: I'll save your note to notes.txt.
```

### Listing directory
```
User: Show me what's in the workspace
Assistant: Let me list the contents of the workspace directory.
```

## Best Practices
1. Always check if a file exists before reading
2. Create backup copies before editing important files
3. Use descriptive file names and paths
4. Organize files in logical directory structures