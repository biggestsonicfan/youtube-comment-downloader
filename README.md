# youtube-comment-downloader
Simple script for downloading Youtube comments without using the Youtube API. The output is in line delimited JSON.

### Installation

Preferably inside a [python virtual environment](https://virtualenv.pypa.io/en/latest/) install this package via:

```
pip install youtube-comment-downloader
```

Or directly from the GitHub repository:

```
pip install https://github.com/biggestsonicfan/youtube-comment-downloader/archive/normalize-id-output.zip
```

### Usage as command-line interface
```
$ youtube-comment-downloader --help
usage: youtube-comment-downloader [--help] [--youtubeid YOUTUBEID] [--url URL] [--output OUTPUT] [--limit LIMIT] [--language LANGUAGE] [--sort SORT]

Download Youtube comments without using the Youtube API

optional arguments:
  --help, -h                             Show this help message and exit
  --youtubeid YOUTUBEID, -y YOUTUBEID    ID of Youtube video for which to download the comments
  --url URL, -u URL                      Youtube URL for which to download the comments
  --output OUTPUT, -o OUTPUT             Output filename (output format is line delimited JSON)
  --pretty, -p                           Change the output format to indented JSON
  --limit LIMIT, -l LIMIT                Limit the number of comments
  --language LANGUAGE, -a LANGUAGE       Language for Youtube generated text (e.g. en)
  --sort SORT, -s SORT                   Whether to download popular (0) or recent comments (1). Defaults to 1
```

For example:
```
youtube-comment-downloader --url https://www.youtube.com/watch?v=ScMzIvxBSi4 --output ScMzIvxBSi4.json
```
or using the Youtube ID:
```
youtube-comment-downloader --youtubeid ScMzIvxBSi4 --output ScMzIvxBSi4.json
```

For Youtube IDs starting with - (dash) you will need to run the script with:
`-y=idwithdash` or `--youtubeid=idwithdash`

### Additionally
You can pass just a valid Youtube url and the comment data will be saved as the Youtube video's ID
```
youtube-comment-downloader https://www.youtube.com/watch?v=lalOy8Mbfdc
```
```
youtube-comment-downloader http://www.youtube.com/watch?v=ishbTyLs6ps&list=PLGup6kBfcU7Le5laEaCLgTKtlDcxMqGxZ&index=106&shuffle=2655
```
```
youtube-comment-downloader http://youtu.be/dQw4w9WgXcQ?feature=youtube_gdata_player
```

### Usage as library
You can also use this script as a library. For instance, if you want to print out the 10 most popular comments for a particular Youtube video you can do the following:


```python
from itertools import islice
from youtube_comment_downloader import *
downloader = YoutubeCommentDownloader()
comments = downloader.get_comments_from_url('https://www.youtube.com/watch?v=ScMzIvxBSi4', sort_by=SORT_BY_POPULAR)
for comment in islice(comments, 10):
    print(comment)
```
