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
* git clone https://github.com/ethael/picogen.git
* cd picogen
* pip install Unidecode beautifulsoup4 md2gemini commonmark Jetforce
* python picogen.py --init
* python picogen.py --generate http
* python picogen.py --serve http
* lynx http://localhost:8000  (lynx is only example. use any web browser you like)

* python picogen.py --generate gemini
* python picogen.py --serve gemini
* amfora gemini://localhost:8000  (amfora is only example. use any gemini browser you like)

# How does it work?
I encourage to check the code. It is short, nice and full of comments. But for those who are happier reading docs, let's dive in!
## TL;DR
1. Clean *target* folder
2. Load configuration from *config.json*
3. Copy everything from *static* folder to *target* folder (css, images, static sources)
4. Load all template files from *templates* folder (and merge them with their parent templates if any)
5. Load all page/article files from *content* folder
    1. Parse header from the beginning of the file
    2. The rest is body and if it is written in markdown, convert it to html and/or gemini
    3. Generate value index for every declared taxonomy (configurable in *config.json*, declared in file header)
    4. Generate article index for every value of every declared taxonomy (configurable in *config.json*, declared in file header)
6. Replace placeholders in templates with generated variables
7. Generate resulting file structure to *target* folder

## Details
### Taxonomy
TBD
### Template
#### Syntax
TBD
#### Inheritance
TBD
#### System variables
TBD
#### Custom variables
TBD
### File descriptor
TBD
### Config options
TBD
### Page/Article file header
TBD
