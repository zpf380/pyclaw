# Web Operations Skill

## Description
This skill provides capabilities for searching the web and fetching web content.

## Commands/Triggers
- "Search for [query]"
- "Find information about [topic]"
- "Fetch webpage [URL]"
- "Get content from [URL]"
- "Look up [information]"

## Implementation
Uses the following tools:
- `web_search(query, count)` - Search the web
- `web_fetch(url, extractMode, maxChars)` - Fetch webpage content

## Examples

### Web search
```
User: Search for Python programming tutorials
Assistant: I'll search the web for Python programming tutorials.
```

### Fetching webpage
```
User: Get the content from example.com
Assistant: I'll fetch the content from example.com for you.
```

### Information lookup
```
User: Find information about machine learning
Assistant: Let me search for information about machine learning.
```

## Best Practices
1. Use specific search queries for better results
2. Limit search results when appropriate (default: 5)
3. Extract content as markdown for better readability
4. Respect website terms of service and robots.txt
5. Cite sources when providing information from the web