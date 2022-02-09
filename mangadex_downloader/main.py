import logging
from pathvalidate import sanitize_filename
from pathlib import Path
from .utils import Language, get_language, validate_url, write_details, valid_cover_types
from .utils import download as download_file
from .errors import InvalidURL
from .fetcher import *
from .manga import Manga
from .chapter import Chapter
from .downloader import ChapterPageDownloader
from .network import Net

log = logging.getLogger(__name__)

__all__ = (
    'download', 'fetch', 'login', 'logout'
)

def login(*args, **kwargs):
    """Login to MangaDex

    Do not worry about token session, the library automatically handle this. 
    Login session will be automtically renewed (unless you called :meth:`logout()`).
    
    Parameters
    -----------
    password: :class:`str`
        Password to login
    username: Optional[:class:`str`]
        Username to login
    email: Optional[:class:`str`]
        Email to login
    
    Raises
    -------
    AlreadyLoggedIn
        User are already logged in
    ValueError
        Parameters are not valid
    LoginFailed
        Login credential are not valid
    """
    Net.requests.login(*args, **kwargs)

def logout():
    """Logout from MangaDex
    
    Raises
    -------
    NotLoggedIn
        User are not logged in
    """
    Net.requests.logout()

def fetch(url, language=Language.English):
    """Fetch the manga

    Parameters
    -----------
    url: :class:`str`
        A MangaDex URL or manga id
    language: :class:`Language` (default: :class:`Language.English`)
        Select a translated language for manga

    Raises
    -------
    InvalidURL
        Not a valid MangaDex url
    InvalidManga
        Given manga cannot be found
    ChapterNotFound
        Given manga has no chapters
    """
    # Parse language
    if isinstance(language, Language):
        lang = language.value
    elif isinstance(language, str):
        lang = get_language(language).value
    else:
        raise ValueError("language must be Language or str, not %s" % language.__class__.__name__)
    log.info("Using %s language" % Language(lang).name)

    log.debug('Validating the url...')
    try:
        manga_id = validate_url(url)
    except InvalidURL as e:
        log.error('%s is not valid mangadex url' % url)
        raise e from None
    
    # Begin fetching
    log.info('Fetching manga %s' % manga_id)
    data = get_manga(manga_id)

    # Append some additional informations
    rels = data['data']['relationships']
    authors = []
    artists = []
    for rel in rels:
        _type = rel.get('type')
        _id = rel.get('id')

        if _type == 'author':
            log.debug('Getting author (%s) manga' % _id)
            authors.append(get_author(_id))

        elif _type == 'artist':
            log.debug('Getting artist (%s) manga' % _id)
            artists.append(get_author(_id))

        elif _type == 'cover_art':
            log.debug('Getting cover (%s) manga' % _id)
            data['cover_art'] = get_cover_art(_id)

    data['authors'] = authors
    data['artists'] = artists

    manga = Manga(data)
    log.info("Found manga \"%s\"" % manga.title)

    # NOTE: After v0.4.0, fetch the chapters first before creating folder for downloading the manga
    # and downloading the cover manga.
    # This will check if selected language in manga has chapters inside of it.
    # If the chapters are not available, it will throw error.
    log.info("Fetching all chapters...")
    chapters = Chapter(get_all_chapters(manga.id, lang), manga.title, lang)
    manga._chapters = chapters

    return manga

def download(
    url,
    folder=None,
    replace=False,
    compressed_image=False,
    start_chapter=None,
    end_chapter=None,
    no_oneshot_chapter=False,
    language=Language.English,
    cover="original"
):
    """Download a manga
    
    Parameters
    -----------
    url: :class:`str`
        A MangaDex URL or manga id
    folder: :class:`str` (default: ``None``)
        Store manga in given folder
    replace: :class:`bool` (default: ``False``)
        Replace manga if exist
    compressed_image: :class:`bool` (default: ``False``)
        Use compressed images for low size when downloading manga
    start_chapter: :class:`float` (default: ``None``)
        Start downloading manga from given chapter
    end_chapter: :class:`float` (default: ``None``)
        Stop downloading manga from given chapter
    no_oneshot_manga: :class:`bool` (default: ``False``)
        If exist, don\'t download oneshot chapter
    language: :class:`Language` (default: :class:`Language.English`)
        Select a translated language for manga

    Raises
    -------
    InvalidURL
        Not a valid MangaDex url
    InvalidManga
        Given manga cannot be found
    ChapterNotFound
        Given manga has no chapters
    """
    # Validate start_chapter and end_chapter param
    if start_chapter is not None and not isinstance(start_chapter, float):
        raise ValueError("start_chapter must be float, not %s" % type(start_chapter))
    if end_chapter is not None and not isinstance(end_chapter, float):
        raise ValueError("end_chapter must be float, not %s" % type(end_chapter))

    if start_chapter > end_chapter:
        raise ValueError("start_chapter cannot be more than end_chapter")

    if cover not in valid_cover_types:
        raise ValueError("invalid cover type, available are: %s" % valid_cover_types)

    manga = fetch(url, language)

    # base path
    base_path = Path('.')

    # Extend the folder
    if folder:
        base_path /= folder
    base_path /= sanitize_filename(manga.title)
    
    # Create folder
    log.debug("Creating folder for downloading")
    base_path.mkdir(parents=True, exist_ok=True)

    # Cover path
    cover_path = base_path / 'cover.jpg'
    log.info('Downloading cover manga %s' % manga.title)

    # Determine cover art quality
    if cover == "original":
        cover_url = manga.cover_art
    elif cover == "512px":
        cover_url = manga.cover_art_512px
    elif cover == "256px":
        cover_url = manga.cover_art_256px

    # Download the cover art
    download_file(cover_url, str(cover_path), replace=True)

    # Write details.json for tachiyomi local manga
    details_path = base_path / 'details.json'
    log.info('Writing details.json')
    write_details(manga, details_path)

    # Begin downloading
    for vol, chap, images in manga.chapters.iter_chapter_images(
        start_chapter,
        end_chapter,
        no_oneshot_chapter,
        compressed_image
    ):
        # Fetching chapter images
        log.info('Getting %s from chapter %s' % (
            'compressed images' if compressed_image else 'images',
            chap
        ))
        images.fetch()

        # Create chapter folder
        chapter_folder = "" # type: str
        # Determine oneshot chapter
        if vol == 0 and chap == "none":
            chapter_folder += "Oneshot"
        elif vol == "none" and chap == "none":
            chapter_folder += "Oneshot"
        elif vol == "none" and chap == "0":
            chapter_folder += "Oneshot"
        else:
            if vol != 'none':
                chapter_folder += 'Volume. %s ' % vol
            chapter_folder += 'Chapter. ' + chap
        
        chapter_path = base_path / chapter_folder
        if not chapter_path.exists():
            chapter_path.mkdir(exist_ok=True)

        while True:
            error = False
            for page, img_url, img_name in images.iter():
                img_path = chapter_path / img_name

                log.info('Downloading %s page %s' % (chapter_folder, page))
                downloader = ChapterPageDownloader(
                    img_url,
                    img_path,
                    replace=replace
                )
                success = downloader.download()

                # One of MangaDex network are having problem
                # Fetch the new one, and start re-downloading
                if not success:
                    log.error('One of MangaDex network are having problem, re-fetching the images...')
                    log.info('Getting %s from chapter %s' % (
                        'compressed images' if compressed_image else 'images',
                        chap
                    ))
                    error = True
                    images.fetch()
                    break
                else:
                    continue
            
            if not error:
                break
                
    log.info("Download finished for manga \"%s\"" % manga.title)
    return manga