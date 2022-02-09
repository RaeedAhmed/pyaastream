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

from pyaastream.terms import formats

url = str
html = str
soup = bs
LOADING = 0
SEARCH = 1
RESULTS = 2
FILES = 3
DOS = platform.system() == "Windows"

BASE = "https://nyaa.si"
TEMPFILE = "tmp.torrent"
TEMPDIR = "webtorrent_tmp"

PLAYER = "mpv" if shutil.which("mpv") else "vlc"


class Prompt:
    query: str
    torrents: list[str]
    torrent: int
    files: list[str]
    show_all_files: bool = False
    show_all_torrents: bool = False


class Torrent(NamedTuple):
    link: str
    title: str
    manifest: str
    size: str
    date: str
    seeders: int


def construct_url() -> url:
    Prompt.query = input(f"Search {BASE}: ")
    filters = {"f": 1, "c": "1_2", "s": "seeders", "o": "desc", "q": Prompt.query}
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
        print("Ctrl-C to exit")
    if context == LOADING:
        pad = "\n" * (round(term_size.lines / 2))
        print(f"{pad}{'Loading...'.center(term_size.columns)}{pad[:-1]}")
    if context == RESULTS:
        print(f"Search results for '{Prompt.query}':")
        torrents = (
            Prompt.torrents
            if Prompt.show_all_torrents
            else Prompt.torrents[: (math.floor(term_size.lines / 2) - 2)]
        )
        for index, torrent in enumerate(torrents):
            print(f"{index:2}:  {torrent.title[:(term_size.columns-5)]}")
            print(
                f"\t\tsize: {torrent.size}, date: {torrent.date}, seeders: {torrent.seeders}"
            )
    if context == FILES:
        files = (
            Prompt.files
            if Prompt.show_all_files
            else [file for file in Prompt.files if any(fmt in file for fmt in formats)]
        )
        print(*files, sep="\n")
        print(f"Page: {Prompt.torrents[int(Prompt.torrent)].link}")


def cli() -> None:
    while True:
        display(SEARCH)
        try:
            Prompt.torrents = get_torrents(http_get(construct_url()))
        except AttributeError:
            continue
        while True:
            display(RESULTS)
            t_choice = input("[b]ack, [t]oggle show all, or Choose torrent: ")
            if t_choice.isdigit() and int(t_choice) in range(len(Prompt.torrents)):
                Prompt.torrent = int(t_choice)
                Prompt.files = fetch_files(Prompt.torrents[Prompt.torrent].manifest)
            elif t_choice == "b":
                break
            elif t_choice == "t":
                Prompt.show_all_torrents = not Prompt.show_all_torrents
                continue
            else:
                continue
            while True:
                display(FILES)
                f_choice = input("[b]ack, [t]oggle show all, or Choose file: ")
                if f_choice.isdigit() and int(f_choice) in range(len(Prompt.files)):
                    try:
                        subprocess.run(
                            shlex.split(
                                f'webtorrent{".cmd"*DOS} download {TEMPFILE} -o {TEMPDIR} -s {f_choice} --{PLAYER}'
                            )
                        )
                    except KeyboardInterrupt:
                        print("Stopping stream")
                elif f_choice == "b":
                    break
                elif f_choice == "t":
                    Prompt.show_all_files = not Prompt.show_all_files
                else:
                    continue


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
