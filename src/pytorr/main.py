import platform
import re
import shlex
import subprocess
import urllib.parse
import urllib.request
from typing import NamedTuple
from urllib.error import HTTPError, URLError

from bs4 import BeautifulSoup as bs

url = str
html = str
soup = bs
BASE = "https://nyaa.si"
TEMPDIR = "webtorrent_tmp"
PLAYER = "mpv"

class Torrent(NamedTuple):
    link: str
    title: str
    magnet: str
    size: str
    date: str
    seeders: int


def construct_url() -> url:
    query = input(f"Search {BASE}: ")
    filters = {"f": 1, "c": "1_2", "s": "seeders", "o": "desc", "q": query}
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
    if not html:
        print("Could not load page")
        exit()
    data = [entry.find_all("td") for entry in html.tbody.find_all("tr")]
    torrents = [
        Torrent(
            link=BASE + datum[1].select("a")[-1].get("href"),
            title=datum[1].select("a")[-1].text,
            magnet=datum[2].select("a")[-1].get("href"),
            size=datum[3].text or "-",
            date=datum[4].text.split(" ")[0] or "-",
            seeders=int(datum[5].text),
        )
        for datum in data
    ]
    return list(filter(lambda torrent: torrent.seeders > 0, torrents))


def list_torrents(torrents: list[Torrent]) -> list[str]:
    return [
        f"{index:2}: {torrent.title}\n\tsize: {torrent.size}, date: {torrent.date}, seeders: {torrent.seeders}"
        for index, torrent in enumerate(torrents)
    ]


def fetch_files(magnet: str) -> list[str]:
    output = (
        subprocess.run(
            shlex.split(f"webtorrent {magnet} -s -o {TEMPDIR}"), capture_output=True
        )
        .stdout.decode("utf-8")
        .splitlines()
    )
    return list(filter(lambda line: re.match("^[0-9]+ ", line), output))


def refresh() -> None:
    subprocess.run("cls" if platform.system() == "Windows" else "clear")
    print("Ctrl-C to exit")


def cli() -> None:
    while True:
        refresh()
        torrents = get_torrents(http_get(construct_url()))
        while True:
            refresh()
            print(*list_torrents(torrents), sep="\n")
            menu1 = input("[b]ack or Choose torrent: ")
            if menu1.isdigit() and int(menu1) in range(len(torrents)):
                files = fetch_files(torrents[int(menu1)].magnet)
            elif menu1 == "b":
                break
            else:
                continue
            while True:
                refresh()
                print(*files, sep="\n")
                print(f"page: {torrents[int(menu1)].link}")
                menu2 = input("[b]ack or Choose file: ")
                if menu2.isdigit() and int(menu2) in range(len(files)):
                    try:
                        subprocess.run(
                            shlex.split(
                                f'webtorrent "{torrents[int(menu1)].magnet}" -s {menu2} --{PLAYER}'
                            )
                        )
                    except KeyboardInterrupt:
                        print("Stopping stream")
                elif menu2 == "b":
                    break
                else:
                    continue


def clean():
    remove = "del" if platform.system() == "Windows" else "rm -rf"
    subprocess.run(shlex.split(f"{remove} {TEMPDIR}"))


def main():
    try:
        cli()
    except KeyboardInterrupt:
        print("\nExiting...")
        exit()
    finally:
        clean()


if __name__ == "__main__":
    main()
