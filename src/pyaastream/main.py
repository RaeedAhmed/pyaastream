import math
import platform
import re
import shlex
import shutil
import subprocess
import urllib.parse
import urllib.request
from typing import NamedTuple
from urllib.error import HTTPError, URLError

from bs4 import BeautifulSoup as bs
from sty import ef, fg, rs

from pyaastream.terms import formats

# type aliases
url = str
html = str
soup = bs

# cli display codes
LOADING = 0
SEARCH = 1
RESULTS = 2
FILES = 3

# change functions if on win
DOS = platform.system() == "Windows"

BASE = "https://nyaa.si"
TEMPFILE = "tmp.torrent"
TEMPDIR = "webtorrent_tmp"
PLAYER = "mpv" if shutil.which("mpv") else "vlc"


class Torrent(NamedTuple):
    link: str
    title: str
    manifest: str
    size: str
    date: str
    seeders: int


class Prompt:
    query: str
    torrents: list[Torrent]
    torrent: int
    files: list[str]
    file_index = -1
    show_all_files: bool = False
    show_all_torrents: bool = False


# text styling
def key(command: str):
    if command.isdigit():
        k, rest = command, ""
    else:
        k, rest = command[0], command[1:]
    return fg(220) + ef.bold + ef.dim + "[" + k + "]" + rs.all + rest


def title(title: str, columns: int, offset=0):
    if len(title) > columns - offset:
        title = title[:columns - offset - 3] + "..."
    return fg(43) + title + rs.all


def info(info: list[str], torrent: Torrent):
    labels = []
    for attr in info:
        labels.append(f"{attr}: {getattr(torrent, attr)}")
    return fg.da_grey + "\t" + ", ".join(labels) + rs.all


def header(header: str, columns=1000):
    if len(header) > columns:
        header = header[:columns-3] + "..."
    return fg(161) + header + rs.all


def construct_url() -> url:
    Prompt.query = input(f"Search {BASE}: ")
    filters = {"f": 1, "c": "1_2", "s": "seeders",
               "o": "desc", "q": Prompt.query}
    params = urllib.parse.urlencode(filters)
    return f"{BASE}?{params}"


def http_get(link: url) -> soup | None:
    try:
        data = urllib.request.urlopen(link)
        if data.info().get_content_subtype() == "html":
            html = data.read().decode("utf-8")
            return bs(html, "lxml")
    except HTTPError as e:
        print(f"Error {e.code}\n{e.read()}")
    except URLError as e:
        print(f"Failed to connected because of {e.reason}")


def get_torrents(html: bs) -> list[Torrent]:
    display(LOADING)
    if not html:
        print("Could not load page")
        exit()
    data = [entry.find_all("td") for entry in html.tbody.find_all("tr")]
    torrents = [
        Torrent(
            link=BASE + datum[1].select("a")[-1].get("href"),
            title=datum[1].select("a")[-1].text,
            manifest=BASE + datum[2].select("a")[0].get("href"),
            size=datum[3].text or "-",
            date=datum[4].text.split(" ")[0] or "-",
            seeders=int(datum[5].text),
        )
        for datum in data
    ]
    return list(filter(lambda torrent: torrent.seeders > 0, torrents))


def fetch_files(manifest: str) -> list[str]:
    display(LOADING)
    urllib.request.urlretrieve(manifest, TEMPFILE)
    output = (
        subprocess.run(
            shlex.split(f"webtorrent{'.cmd'*DOS} {TEMPFILE} -s -o {TEMPDIR}"),
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .splitlines()
    )
    return [line for line in output if re.match("^[0-9]+ ", line)]


def clear():
    subprocess.run(
        shlex.split("cmd /c cls")
        if platform.system() == "Windows"
        else shlex.split("tput reset")
    )


def display(context: int) -> None:
    clear()
    term_size = shutil.get_terminal_size()
    if context == SEARCH:
        print(header("Ctrl-C to exit"))
    if context == LOADING:
        pad = "\n" * (round(term_size.lines / 2))
        print(f"{pad}{'Loading...'.center(term_size.columns)}{pad[:-1]}")
    if context == RESULTS:
        print(header(f"Search results for '{Prompt.query}':"))
        torrents = (
            Prompt.torrents
            if Prompt.show_all_torrents
            else Prompt.torrents[: (math.floor(term_size.lines / 2) - 2)]
        )
        for index, torrent in enumerate(torrents):
            print(
                f"{key(str(index)):28}{title(torrent.title, term_size.columns, offset=6)}")
            print(info(["size", "date", "seeders"], torrent))
    if context == FILES:
        torrent_title = Prompt.torrents[int(Prompt.torrent)].title
        print(header(torrent_title, term_size.columns))
        print(header(f"Page: {Prompt.torrents[int(Prompt.torrent)].link}"))
        files = (
            Prompt.files
            if Prompt.show_all_files
            else [file for file in Prompt.files if any(fmt in file for fmt in formats)]
        )
        for file in files:
            index, file_name = file.split(
                " ")[0], " ".join(file.split(" ")[1:])
            print(key(index), title(file_name, term_size.columns, offset=6))


def cli() -> None:
    if DOS:
        # used to init escape codes on windows cmd
        subprocess.run("", shell=True)
    while True:
        display(SEARCH)
        try:
            Prompt.torrents = get_torrents(http_get(construct_url()))
        except AttributeError:
            continue
        while True:
            display(RESULTS)
            torrent_index = input(
                f"{key('back')}, {key('show all')}, or Choose torrent: ")
            if torrent_index.isdigit() and int(torrent_index) in range(len(Prompt.torrents)):
                Prompt.torrent = int(torrent_index)
                Prompt.files = fetch_files(
                    Prompt.torrents[Prompt.torrent].manifest)
            elif torrent_index == "b":
                break
            elif torrent_index == "s":
                Prompt.show_all_torrents = not Prompt.show_all_torrents
                continue
            else:
                continue
            while True:
                display(FILES)
                last_picked = f" ({Prompt.file_index})" if Prompt.file_index != -1 else ""
                file_index = input(
                    f"{key('back')}, {key('show all')}, or Choose file{last_picked}: ")
                if file_index.isdigit() and int(file_index) in range(len(Prompt.files)):
                    Prompt.file_index = file_index
                    stream_file(file_index)
                elif file_index == "b":
                    Prompt.file_index = -1
                    break
                elif file_index == "s":
                    Prompt.show_all_files = not Prompt.show_all_files
                else:
                    continue


def stream(target, choice=""):
    try:
        subprocess.run(
            shlex.split(
                f'webtorrent{".cmd"*DOS} {target} -o {TEMPDIR} --{PLAYER}'
            )
        )
    except KeyboardInterrupt:
        print("Stopping stream")


def stream_file(file_index):
    return stream(target=TEMPFILE, choice=f"-s {file_index}")


def stream_uri(uri):
    return stream(target=f'"{uri}"')


def direct():
    try:
        stream_uri(input("Enter uri: "))
    except KeyboardInterrupt:
        exit()
    finally:
        shutil.rmtree(TEMPDIR, ignore_errors=True)


def main():
    try:
        cli()
    except KeyboardInterrupt:
        exit()
    finally:
        shutil.rmtree(TEMPDIR, ignore_errors=True)
        try:
            shutil.os.unlink(TEMPFILE)
        except FileNotFoundError:
            pass
        clear()


if __name__ == "__main__":
    main()
