# What is PicoGen?
* Static site generator with support for html and gemini
* Super small implementation - single file with less then 500 lines of code (without comments)
* Featureful - support for categories, tags, custom date format, article read counts, atom feeds, index autogeneration and more...

# What Picogen isn't?
* Big generator with all feature out there, whose code you will never read and understand

# Why bother to make another static site generator?
* I hated that [Hugo](https://github.com/gohugoio/hugo) and [Jekyll](https://github.com/jekyll/jekyll) are too big to fully comprehend and hack at will
* I liked approach of super simple, single file generator like [Makesite](https://github.com/sunainapai/makesite), but wanted something, that is actually usable in real word scenarios.
* I wanted a generator, that would be able to generate both web blog and gemini capsule from single markdown article source 
* I accepted challenge to create single file, full-featured generator with less then 500 lines of code, which will be able to fully replace Hugo/Jekyll on my friends sites.

# Quick start
```
git clone https://github.com/ethael/picogen.git
cd picogen
pip install -r requirements.txt
python picogen.py --init
python picogen.py --generate http
python picogen.py --serve http
lynx http://localhost:8000  # (lynx is only example. use any web browser you like)

python picogen.py --generate gemini
python picogen.py --serve gemini
amfora gemini://localhost:8000  # (amfora is only example. use any gemini browser you like)
```

# How does it work?
I encourage you to check the code. It is short, nice and full of comments. But for those who are happier reading docs, let's dive in!

## TL;DR
1. Cleans *target* folder
2. Loads configuration from *config.json*
3. Copies everything from *static* folder to *target* folder (css, images, static files)
4. Loads all template files from *templates* folder (and merges them with their parent templates if any)
5. Loads all page/article files from *content* folder
    1. Parses metadata header from the beginning of the file
    2. The rest is body - if it's written in markdown, converts it to HTML and/or Gemini
    3. Generates value indexes for every declared taxonomy (so if taxonomy is "tags" then value index is list of tags)
    4. Generates post indexes for every value of every declared taxonomy (so if taxonomy is "tags" then post indexes are lists of posts for every tag)
6. Replaces placeholders in templates with variables (config, metadata, system variables, generated indexes)
7. Exports resulting file structure to *target* folder

## Core Concepts

### Taxonomy System

Taxonomy means categorization or classification. Common examples are tags, categories, blog series, but you can define any taxonomy you want.

**Declaring taxonomies in content:**
```markdown
<!-- tags: Tutorial, Getting Started -->
<!-- series: Getting Started Guide -->
```

Picogen generates two types of indexes for each taxonomy:

1. **Taxonomy Value Posts Index (TVPI)**: Lists all posts that belong to a specific taxonomy value
   - Example: All posts tagged with "Tutorial"
   - Can be generated as a file (e.g., `/tags/tutorial/index.html`) or as a variable for embedding (configured in the config file)

2. **Taxonomy Value Index (TVI)**: Lists all values of a taxonomy with optional post counts
   - Example: A page listing all available tags
   - Can be generated as a file (e.g., `/tags/index.html`) or as a variable for embedding (configured in the config file)

### Templates

Templates use a simple `{{ variable }}` placeholder syntax that gets filled during generation.

#### Syntax

Variables are inserted using double curly braces:
```html
<h1>{{ title }}</h1>
<div>Published: {{ date }}</div>
<div>{{ body }}</div>
```

#### Inheritance

Templates support single-level inheritance using underscore naming convention:
- `child_parent.html` - child template inherits from parent template
- The child content replaces `{{ body }}` in the parent

**Example:**
- `page.html` - base template with `<html>`, `<head>`, navigation, and `{{ body }}`
- `post_page.html` - post template inherits from page.html

When referenced in config as `"template": "post"`, Picogen automatically merges `post_page.html` with `page.html`.

⚠️ WARNING: Never use underscores in the template names unless you want to define an inheritance

#### System Variables

Available in all templates:

| Variable | Description | Example |
|----------|-------------|---------|
| `{{ scheme }}` | URL scheme based on protocol | `http`, `https`, `gemini` |
| `{{ domain }}` | Site domain from config | `example.com` |
| `{{ base_path }}` | Base path for site | `/` or `/blog/` |
| `{{ current_year }}` | Current year | `2025` |
| `{{ rfc3339_now }}` | Current timestamp in RFC3339 | `2025-12-04T13:00:00+01:00` |
| `{{ subtitle }}` | Site subtitle from config | `John Doe's Personal Site` |
| `{{ author }}` | Author name from config | `John Doe` |
| `{{ generator_name }}` | Generator name | `Picogen` |
| `{{ generator_url }}` | Generator URL | GitHub repo |

#### Content File Variables

Available in document templates from file metadata:

| Variable | Description | Source |
|----------|-------------|--------|
| `{{ title }}` | Page/post title | File header: `<!-- title: ... -->` |
| `{{ date }}` | Publication date | File header: `<!-- date: 2024-01-15 -->` |
| `{{ formatted_date }}` | Custom formatted date | Uses `custom_date_format` from config |
| `{{ rfc3339_date }}` | RFC3339 timestamp | Auto-generated from date |
| `{{ body }}` | Converted content | Markdown body converted to HTML/Gemini |
| `{{ summary }}` | First paragraph | Auto-extracted from body |
| `{{ file_name }}` | File name without extension | `welcome-to-picogen` |
| `{{ relative_path }}` | Relative URL path | `/blog/welcome-to-picogen/index.html` |
| `{{ relative_dir_path }}` | Relative directory path | `/blog/welcome-to-picogen` |
| `{{ page_views }}` | View count (optional) | From `page_views_file` if configured |
| `{{ readtime }}` | Reading time in minutes | File header: `<!-- readtime: 3 -->` |

Any custom field in the file header becomes a variable:
```markdown
<!-- custom_field: value -->
```
Can be used as: `{{ custom_field }}`

#### Generated Index Variables

Picogen generates index variables based on taxonomy configuration:

**Format:** `{{ taxonomy_id_index_id }}`

**Examples:**
- `{{ blog_recent-posts }}` - Recent blog posts list
- `{{ tags_simple-list }}` - Comma-separated tag list
- `{{ blog_index-by-date }}` - Date-ordered blog index

For taxonomy value-specific indexes:
**Format:** `{{ taxonomy_id_index_id_normalized-value }}`

**Example:**
- `{{ tags_index_by_value_tutorial }}` - All posts tagged "Tutorial"

#### Taxonomy-Specific Variables

Available in taxonomy index templates:

| Variable | Description | Example |
|----------|-------------|---------|
| `{{ taxonomy_id }}` | Taxonomy identifier | `tags`, `series` |
| `{{ taxonomy_title }}` | Taxonomy display title | `Tags`, `Series` |
| `{{ taxonomy_value }}` | Current taxonomy value | `Tutorial` |
| `{{ taxonomy_value_lower }}` | Lowercase value | `tutorial` |
| `{{ taxonomy_value_normalized }}` | URL-safe value | `getting-started` |
| `{{ taxonomy_value_posts_count }}` | Number of posts | `5` |
| `{{ taxonomy_value_posts_index }}` | Inlined posts list | Generated HTML/Gemini |

### File Headers (Metadata)

Content files start with HTML comment metadata:

```markdown
<!-- date: 2024-01-15 -->
<!-- title: Welcome to Picogen -->
<!-- blog -->
<!-- tags: Tutorial, Getting Started -->
<!-- series: Getting Started Guide -->
<!-- readtime: 3 -->
<!-- template: custom-template -->
<!-- draft -->
```

**Standard Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `date` | No | Publication date (YYYY-MM-DD), defaults to 1970-01-01 |
| `title` | No | Page/post title |
| `template` | No | Override default template |
| `draft` | No | If present, file is skipped during generation |

**Taxonomy Fields:**

Any taxonomy defined in config can be used:
- `blog` or `blog:` - Empty value marks as blog post (both formats are equivalent)
- `tags: Value1, Value2` - Comma-separated values
- `series: Series Name` - Single or comma-separated values

**Custom Fields:**

Any field becomes a template variable:
```markdown
<!-- author_bio: John is a software developer -->
<!-- custom_css: dark-theme -->
```

## Configuration (config.json)

### Global Settings

```json
{
  "generator_name": "Picogen",
  "generator_version": "1.0",
  "generator_url": "https://github.com/ethael/picogen",
  "domain": "example.com",
  "ssl_enabled": "false",
  "base_path": "/",
  "subtitle": "John Doe's Personal Site",
  "author": "John Doe",
  "default_template": "page",
  "custom_date_format": "%B %d, %Y",
  "page_views_file": "views.txt"
}
```

**Field Reference:**

| Field | Type | Description |
|-------|------|-------------|
| `domain` | string | Your site domain (without protocol) |
| `ssl_enabled` | string | `"true"` or `"false"` - affects URL scheme |
| `base_path` | string | Base path for all URLs (usually `/`) |
| `subtitle` | string | Site tagline/description |
| `author` | string | Default author name |
| `default_template` | string | Template used when none specified |
| `custom_date_format` | string | Python strftime format for dates |
| `page_views_file` | string | Optional file with view counts (format: `path:count`) |

### Taxonomy Configuration

Taxonomies are defined in the `taxonomies` array:

```json
{
  "taxonomies": [
    {
      "id": "blog",
      "title": "Blog",
      "document_template": "post",
      "value_posts_indexes": [...],
      "value_indexes": [...]
    }
  ]
}
```

**Taxonomy Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique identifier (used in file headers and variable names) |
| `title` | Yes | Display title for the taxonomy |
| `document_template` | No | Default template for documents with this taxonomy |
| `value_posts_indexes` | No | Array of post index configurations |
| `value_indexes` | No | Array of value index configurations |

### Index Configuration

#### Value Posts Indexes (value_posts_indexes)

Generates lists of posts for each taxonomy value:

```json
{
  "id": "index",
  "template": "blog-index",
  "item_template": "blog-index-item",
  "order_by": "date",
  "order_direction": "desc",
  "limit": "10",
  "output_type": "file",
  "output_suffix": "html",
  "output_path": "sitemap.xml",
  "custom_variables": {
    "feed_url": "/blog/feed.xml"
  }
}
```

**Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Index identifier (used in variable/file names) |
| `template` | Yes | Template for the index wrapper |
| `item_template` | Yes | Template for each post in the index |
| `order_by` | No | Sort field: `date`, `title`, etc. (default: `date`) |
| `order_direction` | No | `asc` or `desc` (default: `desc`) |
| `limit` | No | Maximum number of posts to include |
| `output_type` | Yes | `file` or `variable` |
| `output_suffix` | No | File extension override (e.g., `xml` for feeds) |
| `output_path` | No | Custom output path (e.g., `sitemap.xml` for root) |
| `custom_variables` | No | Dictionary of custom variables for templates |

**Output Types:**
- `file` - Generates file at `/taxonomy-id/value/index-id.suffix`
- `variable` - Creates variable named `taxonomy_id_index_id`

#### Value Indexes (value_indexes)

Generates lists of taxonomy values with optional post counts:

```json
{
  "id": "index",
  "template": "tags-index",
  "item_template": "tags-index-item",
  "order_by": "name",
  "order_direction": "asc",
  "output_type": "file",
  "inlined_index_id": "index_by_value"
}
```

**Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Index identifier |
| `template` | Yes | Template for the index wrapper |
| `item_template` | Yes | Template for each taxonomy value |
| `order_by` | No | `name` (alphabetical) or `count` (by post count) |
| `order_direction` | No | `asc` or `desc` |
| `limit` | No | Maximum number of values to include |
| `output_type` | Yes | `file` or `variable` |
| `inlined_index_id` | No | Embed another index for each value |

**Inlined Indexes:**

The `inlined_index_id` embeds a posts index for each taxonomy value. This creates a combined page showing all values and their posts.

Example: Tags index page with all tags, and under each tag, all posts with that tag.

## Features

### Dual Protocol Support

Generate both HTML and Gemini from the same Markdown source:

```bash
python picogen.py --generate http gemini
```

Protocol-specific files:
- HTML: `content/page.html`, `templates/html/`, `static/html/`
- Gemini: `content/page.gmi`, `templates/gmi/`, `static/gmi/`
- Markdown: `content/page.md` - converts to both protocols

### RSS/Atom Feeds

Configure as a value_posts_index with XML output:

```json
{
  "id": "feed",
  "template": "rss-feed",
  "item_template": "rss-item",
  "order_by": "date",
  "order_direction": "desc",
  "output_type": "file",
  "output_suffix": "xml"
}
```

Output: `/taxonomy-id/feed.xml`

Feed templates should include:
- `rss-feed.xml` - Feed wrapper with `<feed>` tag
- `rss-item.xml` - Entry template with `<entry>` tag

### Sitemap Generation

Configure as a value_posts_index with custom output path:

```json
{
  "id": "sitemap",
  "template": "sitemap",
  "item_template": "sitemap-item",
  "order_by": "date",
  "order_direction": "desc",
  "output_type": "file",
  "output_suffix": "xml",
  "output_path": "sitemap.xml"
}
```

Output: `/sitemap.xml` (at root due to `output_path`)

Sitemap templates:
- `sitemap.xml` - Wrapper with `<urlset>` tag
- `sitemap-item.xml` - URL entry with `<url>`, `<loc>`, `<lastmod>`

### URL Normalization

The `normalize_string()` function creates URL-safe strings:
- Removes accents: `Café` → `Cafe`
- Converts spaces to hyphens: `Getting Started` → `getting-started`
- Lowercases: `Tutorial` → `tutorial`

Use `{{ taxonomy_value_normalized }}` in templates for proper URLs.

### Page Views Tracking

Optional page view counts from external file:

**config.json:**
```json
{
  "page_views_file": "views.txt"
}
```

**views.txt format:**
```
/blog/post-name:150
/projects:45
```

Access in templates: `{{ page_views }}`

### Draft Posts

Mark posts as drafts to skip during generation:

```markdown
<!-- draft -->
```

Posts with `draft` field are completely ignored.

## Example Workflow

### 1. Create a Blog Post

**content/blog/my-first-post.md:**
```markdown
<!-- date: 2025-01-15 -->
<!-- title: My First Post -->
<!-- blog -->
<!-- tags: Tutorial, Beginner -->
<!-- readtime: 5 -->

# My First Post

This is my first blog post with Picogen!
```

### 2. Configure Taxonomy

**config.json:**
```json
{
  "taxonomies": [
    {
      "id": "blog",
      "title": "Blog",
      "document_template": "post",
      "value_posts_indexes": [
        {
          "id": "index",
          "template": "blog-index",
          "item_template": "blog-index-item",
          "output_type": "file"
        }
      ]
    }
  ]
}
```

### 3. Create Templates

**templates/html/post_page.html:**
```html
<article>
  <h1>{{ title }}</h1>
  <div>{{ date }} | {{ readtime }} minutes reading</div>
  {{ body }}
  <div>Tags: {{ tags }}</div>
</article>
```

### 4. Generate

```bash
python picogen.py --generate http gemini
```

**Output:**
- `/target/html/blog/my-first-post/index.html`
- `/target/html/blog/index.html` (blog index)
- `/target/gmi/blog/my-first-post/index.gmi`
- `/target/gmi/blog/index.gmi`

### 5. Serve Locally

```bash
python picogen.py --serve http
# Visit http://localhost:8000

python picogen.py --serve gemini --port 8001
# Visit gemini://localhost:8001
```

## Tips and Best Practices

1. **Template Naming**: Use hyphens for multi-word names (`blog-index.html`), underscores only for inheritance (`post_page.html`)

2. **Variable Debugging**: Check generated variable names in console output during generation

3. **Index Organization**:
   - Use `variable` output for embedding in other pages
   - Use `file` output for standalone index pages

4. **Taxonomy Design**: Start simple with `blog` and `tags`, add more as needed

5. **URL Structure**: Taxonomy values with spaces become hyphenated in URLs automatically

6. **Testing**: Use `--init` to see working examples of all features

7. **Custom Variables**: Add any metadata field to file headers - they all become template variables
