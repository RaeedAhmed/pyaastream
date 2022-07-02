import math
import platform
import re
import shlex
import shutil
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple
from urllib.error import HTTPError, URLError

import tomli
from bs4 import BeautifulSoup as bs
from sty import ef, fg, rs

import pyaastream
from pyaastream.terms import formats

TEMPFILE = Path.home() / "tmp.torrent"
TEMPDIR = Path.home() / "webtorrent_tmp"

DOS = platform.system() == "Windows"

# cli display codes
LOADING = 0
SEARCH = 1
RESULTS = 2
FILES = 3
HISTORY = 4


class Torrent(NamedTuple):
    link: str
    title: str
    manifest: str
    size: str
    date: str
    seeders: int


@dataclass
class Prompt:
    query: str
    link: str
    torrent: int
    torrents: list[Torrent]
    files: list[str]
    file_index: int = -1
    show_all_files: bool = False
    show_all_torrents: bool = False


def load_config() -> dict[str, dict[str, int | str]]:
    default_path = Path(pyaastream.__path__[0]) / "config.toml"
    if not DOS:
        config_file = Path.home() / ".config" / "pyaastream" / "config.toml"
        if not config_file.exists():
            shutil.copy(default_path, config_file)
    while True:
        try:
            with open(config_file, "rb") as f:
                config = tomli.load(f)
            break
        except tomli.TOMLDecodeError:
            return None
    return config


while True:
    config = load_config()
    if config is not None:
        break
    else:
        input("Invalid config file.")

if log := config['history']['location'] == "default":
    if DOS:
        log = Path(__file__).absolute().parent / "history.txt"
    else:
        cache_dir = Path(Path.home() / ".cache" / "pyaastream").mkdir(exist_ok=True, parents=True)
        log = cache_dir / "history.txt"


def write_history(torrent: Torrent, entry: str) -> None:
    if config['history']['record']:
        with open(log, "a") as file:
            record = "||".join([torrent.title, torrent.manifest, entry])
            file.write(record + "\n")


class InvalidURI(Exception):
    pass


class Style:
    @staticmethod
    def key(command: str):
        if command.isdigit():
            k, rest = command, ""
        else:
            k, rest = command[0], command[1:]
        return fg(220) + ef.bold + ef.dim + "[" + k + "]" + rs.all + rest

    @staticmethod
    def title(title: str, columns: int, offset=0):
        if len(title) > columns - offset:
            title = title[: columns - offset - 3] + "..."
        return fg(43) + title + rs.all

    @staticmethod
    def info(info: list[str], torrent: Torrent):
        labels = []
        for attr in info:
            labels.append(f"{attr}: {getattr(torrent, attr)}")
        return fg.da_grey + "\t" + ", ".join(labels) + rs.all

    @staticmethod
    def header(header: str, columns=1000):
        if len(header) > columns:
            header = header[: columns - 3] + "..."
        return fg(161) + header + rs.all


def http_get(request: callable, link: str):
    try:
        return request(link)
    except HTTPError as e:
        print(f"Error {e.code}\n{e.read()}")
    except URLError as e:
        print(f"Failed to connect because of {e.reason}")


def soup(link: str):
    data = urllib.request.urlopen(link)
    if data.info().get_content_subtype() == "html":
        html = data.read().decode("utf-8")
        return bs(html, "lxml")


def fetch_files(link: str):
    try:
        if link.endswith(".torrent"):
            if not http_get(
                lambda url: urllib.request.urlretrieve(url, TEMPFILE), link
            ):
                return None
            command = f"webtorrent{'.cmd'*DOS} {TEMPFILE} -s -o {TEMPDIR}"
        elif link.startswith("magnet:"):
            command = f'webtorrent{".cmd"*DOS} "{link}" -s -o {TEMPDIR}'
        else:
            raise InvalidURI
    except InvalidURI:
        print("Not a torrent or magnet file. Try again.")
        return None
    output = (
        subprocess.run(
            shlex.split(command),
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


def display(context: int, message=""):
    clear()
    term_size = shutil.get_terminal_size()
    if context == SEARCH:
        print(Style.header("Ctrl-C to exit"))
    elif context == RESULTS:
        print(Style.header(f"Search results for '{Prompt.query}':"))
        torrents = (
            Prompt.torrents
            if Prompt.show_all_torrents
            else Prompt.torrents[: (math.floor(term_size.lines / 2) - 2)]
        )
        for index, torrent in enumerate(torrents):
            print(f"{Style.key(str(index)):28}{Style.title(torrent.title, term_size.columns, offset=6)}")
            print(Style.info(["size", "date", "seeders"], torrent))
    elif context == FILES:
        files = (
            Prompt.files
            if Prompt.show_all_files
            else [file for file in Prompt.files if any(fmt in file for fmt in formats)]
        )
        for file in files:
            index, file_name = file.split(" ")[0], " ".join(file.split(" ")[1:])
            print(Style.key(index), Style.title(file_name, term_size.columns, offset=6))
    elif context == HISTORY:
        pass


def stream(target, file_choice=" ", subtitle="", streaming=True):
    player = config["playback"]["player"]
    player_args = config["playback"]["player_args"]
    command = shlex.split(
        f'webtorrent{".cmd"*DOS} {"download "*(not streaming)}{target} -o {TEMPDIR}{file_choice}'
        + f' --{player} --player-args="{player_args}{subtitle}"' * streaming
    )
    try:
        subprocess.run(command)
    except KeyboardInterrupt:
        print("Stopping stream")


def stream_file(file_index, manifest=TEMPFILE, streaming=True):
    return stream(target=manifest, file_choice=f" -s {file_index}", streaming=streaming)


def stream_uri(uri, subtitle=""):
    return stream(target=f'"{uri}"', subtitle=subtitle)


class Record(NamedTuple):
    torrent_title: str
    manifest: str
    file_info: str


def jump_to_history():
    with open(log, "r") as file:
        records = file.readlines()
    history = [Record(record.split("||")) for record in records]
    while True:
        display(HISTORY)
        selection = input("Select entry: ")


def nyaa():
    BASE = "https://nyaa.si"

    def construct_url():
        params = {k[0]: v for k, v in config["nyaa"].items()}
        params["q"] = Prompt.query
        return f"https://nyaa.si/?{urllib.parse.urlencode(params)}"

    def request(link):
        data = urllib.request.urlopen(link)
        html = data.read().decode("utf-8")
        return bs(html, "lxml")

    def get_torrents(html: bs):
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

    def cli():
        while True:
            display(SEARCH)
            Prompt.query = input(f"Search nyaa.si or {Style.key('history')}: ")
            if Prompt.query in ["h", "history", "H"]:
                Prompt.torrents = jump_to_history()
                exit()
            else:
                try:
                    Prompt.torrents = get_torrents(http_get(request, construct_url()))
                except AttributeError:
                    continue
            while True:
                display(RESULTS)
                torrent_index = input(
                    f"{Style.key('back')}, {Style.key('show all')}, or Choose torrent: ")
                if torrent_index.isdigit() and int(torrent_index) in range(len(Prompt.torrents)):
                    Prompt.torrent = int(torrent_index)
                    Prompt.files = fetch_files(Prompt.torrents[Prompt.torrent].manifest)
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
                    file_index = input(f"{Style.key('back')}, {Style.key('show all')}, or Choose file{last_picked}: ")
                    if file_index.isdigit() and int(file_index) in range(len(Prompt.files)):
                        Prompt.file_index = file_index
                        write_history(Prompt.torrents[Prompt.torrent], Prompt.files[int(file_index)])
                        stream_file(file_index)
                    elif file_index == "b":
                        Prompt.file_index = -1
                        break
                    elif file_index == "s":
                        Prompt.show_all_files = not Prompt.show_all_files
                    else:
                        continue

    main(cli)


def subtitle_paths():
    return ":".join(set([str(track.parent) for track in list(TEMPDIR.rglob("*.srt"))]))


def torr():
    def cli():
        while True:
            display(SEARCH)
            link = input("Enter torrent or magnet link: ")
            Prompt.files = fetch_files(link)
            if Prompt.files:
                while True:
                    display(FILES)
                    last_picked = (f" ({Prompt.file_index})" if Prompt.file_index != -1 else "")
                    file_index = input(
                        f"{Style.key('back')}, {Style.key('show all')}, select {Style.key('all')}, or Choose file{last_picked}: ")
                    if file_index.isdigit() and int(file_index) in range(len(Prompt.files)):
                        Prompt.file_index = file_index
                        streaming = any(fmt in Prompt.files[int(file_index)] for fmt in formats)
                        stream_file(file_index, manifest=link, streaming=streaming)
                    elif file_index == "b":
                        Prompt.file_index = -1
                        break
                    elif file_index == "s":
                        Prompt.show_all_files = not Prompt.show_all_files
                    elif file_index == "a":
                        stream_uri(link, f" --sub-file-paths={subtitle_paths()}")
                    else:
                        continue
    main(cli)


def main(cli: callable):
    if DOS:
        # used to init escape codes on windows cmd
        subprocess.run("", shell=True)
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
