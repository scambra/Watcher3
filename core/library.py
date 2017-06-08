import os
import json
from hachoir.parser import createParser
from hachoir.metadata import extractMetadata
from core import sqldb, searchresults, plugins
import core
from core.movieinfo import TMDB
from core.helpers import Url, Conversions
import PTN
import datetime
import logging
import uuid
import xml.etree.cElementTree as ET
import csv
import shutil
import threading

logging = logging.getLogger(__name__)

sql = sqldb.SQL()

MOVIES_cols = [i.name for i in sql.MOVIES.c]


class ImportDirectory(object):

    def __init__(self):
        return

    @staticmethod
    def scan_dir(directory, minsize=500, recursive=True):
        ''' Scans directory for movie files
        directory: str base directory of movie library
        minsize: int minimum filesize in MB <default 500>
        recursive: bool scan recursively or just root directory <default True>

        Returns list of files
        '''

        logging.info('Scanning {} for movies.'.format(directory))

        files = []
        try:
            if recursive:
                files = ImportDirectory._walk(directory)
            else:
                files = [os.path.join(directory, i) for i in os.listdir(directory) if os.path.isfile(os.path.join(directory, i))]
        except Exception as e:
            return {'error': str(e)}

        files = [i for i in files if os.path.getsize(i) >= (minsize * 1024**2)]

        return {'files': files}

    @staticmethod
    def _walk(directory):
        ''' Recursively gets all files in dir
        dir: directory to scan for files

        Returns list of absolute file paths
        '''

        files = []
        dir_contents = os.listdir(directory)
        for i in dir_contents:
            logging.info('Scanning {}{}{}'.format(directory, os.sep, i))
            full_path = os.path.join(directory, i)
            if os.path.isdir(full_path):
                files = files + ImportDirectory._walk(full_path)
            else:
                files.append(full_path)
        return files


class ImportKodiLibrary(object):

    @staticmethod
    def get_movies(url):
        ''' Gets list of movies from kodi server
        url: str url of kodi server

        url should include auth info if required.

        Gets movies from kodi, reformats list, and adds resolution/source info.
        Since Kodi doesn't care about souce we default to BluRay-<resolution>

        Returns list of dicts of movies
        '''

        krequest = {"jsonrpc": "2.0",
                    "method": "VideoLibrary.GetMovies",
                    "params": {
                        "filter": {
                            "field": "playcount",
                            "operator": "is",
                            "value": "0"
                        },
                        "limits": {
                            "start": 0,
                            "end": 0
                        },
                        "properties": [
                            "title",
                            "year",
                            "imdbnumber",
                            "file",
                            "streamdetails"
                        ],
                        "sort": {
                            "order": "ascending",
                            "method": "label",
                            "ignorearticle": True
                        }
                    },
                    "id": "libMovies"
                    }

        logging.info('Retreiving movies from Kodi.')
        url = '{}/jsonrpc?request={}'.format(url, json.dumps(krequest))

        try:
            response = Url.open(url)
        except Exception as e:
            logging.error('Unable to reach Kodi server.', exc_info=True)
            return {'response': False, 'error': str(e.args[0].reason).split(']')[-1]}

        if response.status_code != 200:
            if response.status_code == 401:
                return {'response': False, 'error': 'Incorrect credentials.'}
            elif response.status_code == 403:
                return {'response': False, 'error': 'Unauthorized credentials.'}
            elif response.status_code == 404:
                return {'response': False, 'error': 'Server not found.'}
            else:
                return {'response': False, 'error': 'Error {}'.format(response.status_code)}

        library = [i['imdbid'] for i in sql.get_user_movies()]
        movies = []

        today = str(datetime.date.today())
        for i in json.loads(response.text)['result']['movies']:

            if i['imdbnumber'] in library:
                logging.info('{} in library, skipping.'.format(i['imdbnumber']))
                continue

            movie = {}
            movie['title'] = i['title']
            movie['year'] = i['year']
            movie['imdbid'] = i['imdbnumber']
            movie['file'] = i['file']
            movie['added_date'] = movie['finished_date'] = today
            movie['audiocodec'] = i['streamdetails']['audio'][0].get('codec') if i['streamdetails']['audio'] else ''
            if movie['audiocodec'] == 'dca' or movie['audiocodec'].startswith('dts'):
                movie['audiocodec'] = 'DTS'
            if i['streamdetails']['video']:
                movie['videocodec'] = i['streamdetails']['video'][0].get('codec')
                width = i['streamdetails']['video'][0]['width']
                if width > 1920:
                    movie['resolution'] = 'BluRay-4K'
                elif 1920 >= width > 1440:
                    movie['resolution'] = 'BluRay-1080P'
                elif 1440 >= width > 720:
                    movie['resolution'] = 'BluRay-720P'
                else:
                    movie['resolution'] = 'DVD-SD'
            else:
                movie['videocodec'] = movie['resolution'] = ''

            movies.append(movie)

        return {'response': True, 'movies': movies}


class ImportPlexLibrary(object):

    @staticmethod
    def get_libraries(url, token):
        ''' Gets list of libraries in server url
        url: url and port of plex server
        token: plex auth token for server

        Returns list of dicts
        '''

        headers = {'X-Plex-Token': token}

        url = '{}/library/sections'.format(url)

        try:
            r = Url.open(url, headers=headers)
            xml = r.text
        except Exception as e:  # noqa
            logging.error('Unable to contact Plex server.', exc_info=True)
            return {'response', False, 'error', 'Unable to contact Plex server.'}

        libs = []
        try:
            root = ET.fromstring(xml)

            for directory in root.findall('Directory'):
                lib = directory.attrib
                lib['path'] = directory.find('Location').attrib['path']
                libs.append(lib)
        except Exception as e:  # noqa
            logging.error('Unable to parse Plex xml.', exc_info=True)
            return {'response', False, 'error', 'Unable to parse Plex xml.'}

        return {'response': True, 'libraries': libs}

    @staticmethod
    def get_movies(server, libid, token):

        headers = {'X-Plex-Token': token}
        url = '{}/library/sections/{}/all'.format(server, libid)

        try:
            r = Url.open(url, headers=headers)
            xml = r.text
        except Exception as e:  # noqa
            logging.error('Unable to contact Plex server.', exc_info=True)
            return {'response', False, 'error', 'Unable to contact Plex server.'}

        movies = []
        try:
            root = ET.fromstring(xml)

            for i in root:
                movie = {}

                movies.append(movie)

        except Exception as e:  # noqa
            logging.error('Unable to parse Plex xml.', exc_info=True)
            return {'response', False, 'error', 'Unable to parse Plex xml.'}

        return {'response': True, 'movies': movies}

    @staticmethod
    def get_token(username=None, password=None):
        ''' Gets auth token for plex
        username: str username of plex account
        password: str password of plex account

        Returns str token or None
        '''

        plex_url = 'https://plex.tv/users/sign_in.json'
        post_data = {'user[login]': username,
                     'user[password]': password
                     }
        headers = {'X-Plex-Client-Identifier': str(uuid.getnode()),
                   'X-Plex-Product': 'Watcher',
                   'X-Plex-Version': '1.0'}

        try:
            r = Url.open(plex_url, post_data=post_data, headers=headers)
            return json.loads(r.text)['user'].get('authentication_token')
        except Exception as e:  # noqa
            logging.error('Unable to get Plex token.', exc_info=True)
            return None

    @staticmethod
    def read_csv(csv_text):
        library = [i['imdbid'] for i in sql.get_user_movies()]
        try:
            movies = []
            reader = csv.DictReader(csv_text.splitlines())
            for row in reader:
                movies.append(dict(row))
        except Exception as e:  # noqa
            return {'response': False, 'error': e}

        parsed_movies = []
        incomplete = []
        today = str(datetime.date.today())
        try:
            for movie in movies:
                complete = True
                parsed = {}

                db_id = movie['MetaDB Link'].split('/')[-1]
                if db_id.startswith('tt'):
                    if db_id in library:
                        continue
                    else:
                        parsed['imdbid'] = db_id
                elif db_id.isdigit():
                    parsed['tmdbid'] = db_id
                else:
                    parsed['imdbid'] = ''
                    complete = False

                parsed['title'] = movie['Title']
                parsed['year'] = movie['Year']

                parsed['added_date'] = parsed['finished_date'] = today

                parsed['audiocodec'] = movie['Audio Codec']
                if parsed['audiocodec'] == 'dca' or parsed['audiocodec'].startswith('dts'):
                    parsed['audiocodec'] = 'DTS'

                width = int(movie['Width'])
                if width > 1920:
                    parsed['resolution'] = 'BluRay-4K'
                elif 1920 >= width > 1440:
                    parsed['resolution'] = 'BluRay-1080P'
                elif 1440 >= width > 720:
                    parsed['resolution'] = 'BluRay-720P'
                else:
                    parsed['resolution'] = 'DVD-SD'

                parsed['size'] = int(movie['Part Size as Bytes'])
                parsed['file'] = movie['Part File']

                if complete:
                    parsed_movies.append(parsed)
                else:
                    incomplete.append(parsed)
        except Exception as e:
            logging.error('Error parsing Plex CSV.', exc_info=True)
            return {'response': False, 'error': 'Unable to parse CSV file.'}

        return {'response': True, 'complete': parsed_movies, 'incomplete': incomplete}


class ImportCPLibrary(object):

    @staticmethod
    def get_movies(url):
        ''' Gets list of movies from CP
        url: str full url of cp movies.list api call

        Returns list of dicts of movie info
        '''

        try:
            r = Url.open(url)
        except Exception as e:
            return {'response': False, 'error': str(e)}
        if r.status_code != 200:
            return {'response': False, 'error': 'Error {}'.format(r.status_code)}
        try:
            cp = json.loads(r.text)
        except Exception as e:
            return {'response': False, 'error': 'Malformed json response from CouchPotato'}

        if cp['total'] == 0:
            return ['']

        library = [i['imdbid'] for i in sql.get_user_movies()]
        movies = []
        for m in cp['movies']:
            if m['info']['imdb'] in library:
                continue
            movie = {}
            if m['status'] == 'done':
                movie['status'] = 'Disabled'
                for i in m['releases']:
                    if i['status'] == 'done':
                        name = i['info']['name']
                        title_data = PTN.parse(name)

                        movie['audiocodec'] = title_data.get('audio')
                        movie['videocodec'] = title_data.get('codec')

                        movie['size'] = i['info']['size'] * 1024 * 1024
                        if '4K' in name or 'UHD' in name or '2160P' in name:
                            movie['resolution'] = 'BluRay-4K'
                        elif '1080' in name:
                            movie['resolution'] = 'BluRay-1080P'
                        elif '720' in name:
                            movie['resolution'] = 'BluRay-720P'
                        else:
                            movie['resolution'] = 'DVD-SD'
                        break
                movie.setdefault('size', 0)
                movie['quality'] = 'Default'
            else:
                movie['status'] = 'Waiting'

            movie.setdefault('resolution', 'BluRay-1080P')

            movie['title'] = m['info']['original_title']
            movie['year'] = m['info']['year']
            movie['overview'] = m['info']['plot']
            movie['poster_path'] = '/{}'.format(m['info']['images']['poster_original'][0].split('/')[-1])
            movie['url'] = 'https://www.themoviedb.org/movie/{}'.format(m['info']['tmdb_id'])
            movie['vote_average'] = m['info']['rating']['imdb'][0]
            movie['imdbid'] = m['info']['imdb']
            movie['id'] = m['info']['tmdb_id']
            movie['release_date'] = m['info']['released']
            movie['alternative_titles'] = {'titles': [{'iso_3166_1': 'US',
                                                       'title': ','.join(m['info']['titles'])
                                                       }]
                                           }
            movie['release_dates'] = {'results': []}

            movies.append(movie)

        return {'response': True, 'movies': movies}


class Metadata(object):
    ''' Methods for gathering/preparing metadata for movies
    '''

    def __init__(self):
        self.tmdb = TMDB()
        return

    def from_file(self, filepath):
        ''' Gets video metadata using hachoir.parser
        filepath: str absolute path to movie file

        On failure can return empty dict

        Returns dict
        '''

        logging.info('Gathering metadata for {}.'.format(filepath))

        data = {
            'title': None,
            'year': None,
            'resolution': None,
            'rated': None,
            'imdbid': None,
            'videocodec': None,
            'audiocodec': None,
            'releasegroup': None,
            'source': None,
            'quality': None,
            'path': filepath
        }

        titledata = self.parse_filename(filepath)
        data.update(titledata)

        filedata = self.parse_media(filepath)
        data.update(filedata)

        if data.get('resolution'):
            if data['resolution'].upper() in ('4K', '1080P', '720P'):
                data['resolution'] = '{}-{}'.format(data['source'] or 'BluRay', data['resolution'].upper())
            else:
                data['resolution'] = 'DVD-SD'

        if data.get('title') and not data.get('imdbid'):
            title_date = '{} {}'.format(data['title'], data['year']) if data.get('year') else data['title']
            tmdbdata = self.tmdb.search(title_date, single=True)
            if tmdbdata:
                data['year'] = tmdbdata['release_date'][:4]
                data.update(tmdbdata)
                data['imdbid'] = self.tmdb.get_imdbid(data['id'])
            else:
                logging.warning('Unable to get data from TMDB for {}'.format(data['imdbid']))
                return data

        return data

    def parse_media(self, filepath):
        ''' Uses Hachoir-metadata to parse the file header to metadata
        filepath: str absolute path to file

        Attempts to get resolution from media width

        Returns dict of metadata
        '''

        metadata = {}
        try:
            with createParser(filepath) as parser:
                extractor = extractMetadata(parser)
            filedata = extractor.exportDictionary(human=False)
            parser.stream._input.close()

        except Exception as e:  # noqa
            logging.error('Unable to parse metadata from file header.', exc_info=True)
            return metadata

        if filedata:
            if filedata.get('Metadata'):
                width = filedata['Metadata'].get('width')
            elif metadata.get('video[1]'):
                width = filedata['video[1]'].get('width')
            else:
                width = None

            if width:
                width = int(width)
                if width > 1920:
                    filedata['resolution'] = '4K'
                elif 1920 >= width > 1440:
                    filedata['resolution'] = '1080P'
                elif 1440 >= width > 720:
                    filedata['resolution'] = '720P'
                else:
                    filedata['resolution'] = 'SD'
            else:
                filedata['resolution'] = 'SD'

            if filedata.get('audio[1]'):
                metadata['audiocodec'] = filedata['audio[1]'].get('compression').replace('A_', '')
            if filedata.get('video[1]'):
                metadata['videocodec'] = filedata['video[1]'].get('compression').split('/')[0].replace('V_', '')

        return metadata

    def parse_filename(self, filepath):
        ''' Uses PTN to get as much info as possible from path
        filepath: str absolute path to file

        Returns dict of Metadata
        '''
        logging.info('Parsing {} for movie information.'.format(filepath))

        titledata = PTN.parse(os.path.basename(filepath))
        # this key is useless
        if 'excess' in titledata:
            titledata.pop('excess')

        if len(titledata) < 3:
            logging.info('Parsing filename doesn\'t look accurate. Parsing parent folder name.')

            path_list = os.path.split(filepath)[0].split(os.sep)
            titledata = PTN.parse(path_list[-1])
            logging.info('Found {} in parent folder.'.format(titledata))
        else:
            logging.info('Found {} in filename.'.format(titledata))

        title = titledata.get('title')
        if title and title[-1] == '.':
            titledata['title'] = title[:-1]

        # Make sure this matches our key names
        if 'year' in titledata:
            titledata['year'] = str(titledata['year'])
        titledata['videocodec'] = titledata.pop('codec', None)
        titledata['audiocodec'] = titledata.pop('audio', None)
        titledata['source'] = titledata.pop('quality', None)
        titledata['releasegroup'] = titledata.pop('group', None)

        return titledata

    def convert_to_db(self, movie):
        ''' Takes movie data and converts to a database-writable dict
        movie: dict of movie information

        Used to prepare TMDB's movie response for write into MOVIES
        Must include Watcher-specific keys ie resolution,
        Makes sure all keys match and are present.
        Sorts out alternative titles and digital release dates

        Returns dict ready to sql.write into MOVIES
        '''

        if not movie.get('imdbid'):
            movie['imdbid'] = 'N/A'

        if not movie.get('year') and movie.get('release_date'):
            movie['year'] = movie['release_date'][:4]
        elif not movie.get('year'):
            movie['year'] = 'N/A'

        if movie.get('added_date') is None:
            movie['added_date'] = str(datetime.date.today())

        movie['poster'] = 'images/poster/{}.jpg'.format(movie['imdbid'])
        movie['plot'] = movie['overview']
        movie['url'] = 'https://www.themoviedb.org/movie/{}'.format(movie['id'])
        movie['score'] = movie['vote_average']

        if not movie.get('status'):
            movie['status'] = 'Waiting'
        movie['added_date'] = str(datetime.date.today())
        movie['backlog'] = 0
        movie['tmdbid'] = movie['id']

        a_t = []
        for i in movie.get('alternative_titles', {}).get('titles', []):
            if i['iso_3166_1'] == 'US':
                a_t.append(i['title'])

        movie['alternative_titles'] = ','.join(a_t)

        dates = []
        for i in movie.get('release_dates', {}).get('results', []):
            for d in i['release_dates']:
                if d['type'] == 4:
                    dates.append(d['release_date'])

        if dates:
            movie['digital_release_date'] = max(dates)[:10]

        if movie.get('quality') is None:
            movie['quality'] = 'Default'

        movie['finished_file'] = movie.get('finished_file')

        for k, v in movie.items():
            if isinstance(v, str):
                movie[k] = v.strip()

        movie = {k: v for k, v in movie.items() if k in MOVIES_cols}

        return movie


class Manage(object):
    ''' Methods to manipulate status of movies or search results
    '''

    def __init__(self):
        self.sql = sqldb.SQL()
        self.score = searchresults.Score()
        self.tmdb = TMDB()
        self.metadata = Metadata()
        self.poster = Poster()
        self.plugins = plugins.Plugins()

    def add_movie(self, data, origin='Search', full_metadata=False):
        ''' Adds movie to Wanted list.
        :param data: str json.dumps(dict) of info to add to database.
        full_metadata: bool if data is complete and ready for write

        data MUST inlcude tmdb id as data['id']

        Writes data to MOVIES table.

        If full_metadata is False, searches tmdb for data['id'] and updates data

        If Search on Add enabled,
            searches for movie immediately in separate thread.
            If Auto Grab enabled, will snatch movie if found.

        Returns dict of status and message ie {'response': False, 'error': 'Something broke'}
        '''

        response = {}
        tmdbid = data['id']

        if not full_metadata:
            movie = self.tmdb._search_tmdbid(tmdbid)[0]
            movie.update(data)
        else:
            movie = data

        if self.sql.row_exists('MOVIES', imdbid=movie['imdbid']):
            logging.info('{} already exists in library.'.format(movie['title']))

            response['response'] = False

            response['error'] = '{} already exists in library.'.format(movie['title'])
            return response

        movie['quality'] = data.get('quality', 'Default')
        movie['status'] = data.get('status', 'Waiting')
        movie['origin'] = movie.get('origin', origin)

        if movie.get('poster_path'):
            poster_url = 'http://image.tmdb.org/t/p/w300{}'.format(movie['poster_path'])
        else:
            poster_url = 'static/images/missing_poster.jpg'

        movie = self.metadata.convert_to_db(movie)

        if not self.sql.write('MOVIES', movie):
            response['response'] = False
            response['error'] = 'Could not write to database.'
            return response
        else:
            t2 = threading.Thread(target=self.poster.save_poster, args=(movie['imdbid'], poster_url))
            t2.start()

            response['response'] = True
            response['message'] = '{} {} added to library.'.format(movie['title'], movie['year'])
            response['movie'] = movie
            self.plugins.added(movie['title'], movie['year'], movie['imdbid'], movie['quality'])

            return response

    def searchresults(self, guid, status, movie_info=None):
        ''' Marks searchresults status
        :param guid: str download link guid
        :param status: str status to set
        movie_info: dict of movie metadata  <optional>

        If guid is in SEARCHRESULTS table, marks it as status.

        If guid not in SEARCHRESULTS, uses movie_info to create a result.

        Returns Bool on success/fail
        '''

        TABLE = 'SEARCHRESULTS'

        logging.info('Marking guid {} as {}.'.format(guid.split('&')[0], status))

        if self.sql.row_exists(TABLE, guid=guid):

            # Mark bad in SEARCHRESULTS
            logging.info('Marking {} as {} in SEARCHRESULTS.'.format(guid.split('&')[0], status))
            if not self.sql.update(TABLE, 'status', status, 'guid', guid):
                logging.error('Setting SEARCHRESULTS status of {} to {} failed.'.format(guid.split('&')[0], status))
                return False
            else:
                logging.info('Successfully marked {} as {} in SEARCHRESULTS.'.format(guid.split('&')[0], status))
                return True
        else:
            logging.info('Guid {} not found in SEARCHRESULTS, attempting to create entry.'.format(guid.split('&')[0]))
            if movie_info is None:
                logging.warning('Metadata not supplied, unable to create SEARCHRESULTS entry.')
                return False
            search_result = searchresults.generate_simulacrum(movie_info)
            search_result['indexer'] = 'Post-Processing Import'
            search_result['title'] = movie_info['title']
            search_result['size'] = os.path.getsize(movie_info.get('orig_filename', '.'))
            if not search_result['resolution']:
                search_result['resolution'] = 'Unknown'

            search_result = self.score.score([search_result], imported=True)[0]

            required_keys = ('score', 'size', 'status', 'pubdate', 'title', 'imdbid', 'indexer', 'date_found', 'info_link', 'guid', 'torrentfile', 'resoluion', 'type', 'downloadid', 'freeleech')

            search_result = {k: v for k, v in search_result.items() if k in required_keys}

            if self.sql.write('SEARCHRESULTS', search_result):
                return True
            else:
                return False

    def markedresults(self, guid, status, imdbid=None):
        ''' Marks markedresults status

        :param guid: str download link guid
        :param status: str status to set
        :param imdbid: str imdb identification number   <optional>

        If guid is in MARKEDRESULTS table, marks it as status.
        If guid not in MARKEDRSULTS table, created entry. Requires imdbid.

        Returns Bool on success/fail
        '''

        TABLE = 'MARKEDRESULTS'

        if self.sql.row_exists(TABLE, guid=guid):
            # Mark bad in MARKEDRESULTS
            logging.info('Marking {} as {} in MARKEDRESULTS.'.format(guid.split('&')[0], status))
            if not self.sql.update(TABLE, 'status', status, 'guid', guid):
                logging.info('Setting MARKEDRESULTS status of {} to {} failed.'.format(guid.split('&')[0], status))
                return False
            else:
                logging.info('Successfully marked {} as {} in MARKEDRESULTS.'.format(guid.split('&')[0], status))
                return True
        else:
            logging.info('Guid {} not found in MARKEDRESULTS, creating entry.'.format(guid.split('&')[0]))
            if imdbid:
                DB_STRING = {}
                DB_STRING['imdbid'] = imdbid
                DB_STRING['guid'] = guid
                DB_STRING['status'] = status
                if self.sql.write(TABLE, DB_STRING):
                    logging.info('Successfully created entry in MARKEDRESULTS for {}.'.format(guid.split('&')[0]))
                    return True
                else:
                    logging.error('Unable to create entry in MARKEDRESULTS for {}.'.format(guid.split('&')[0]))
                    return False
            else:
                logging.warning('Imdbid not supplied or found, unable to add entry to MARKEDRESULTS.')
                return False

    def movie_status(self, imdbid):
        ''' Updates Movie status.
        :param imdbid: str imdb identification number (tt123456)

        Updates Movie status based on search results.
        Always sets the status to the highest possible level.

        Returns str new movie status or bool False on failure
        '''

        local_details = self.sql.get_movie_details('imdbid', imdbid)
        if local_details:
            current_status = local_details.get('status')
        else:
            return False

        if current_status == 'Disabled':
            return 'Disabled'

        result_status = self.sql.get_distinct('SEARCHRESULTS', 'status', 'imdbid', imdbid)
        if result_status is False:
            logging.error('Could not get SEARCHRESULTS statuses for {}'.format(imdbid))
            return False
        elif 'Finished' in result_status:
            status = 'Finished'
        elif 'Snatched' in result_status:
            status = 'Snatched'
        elif 'Available' in result_status:
            status = 'Found'
        elif local_details.get('predb') == 'found':
            status = 'Wanted'
        else:
            status = 'Waiting'

        logging.info('Setting MOVIES {} status to {}.'.format(imdbid, status))
        if self.sql.update('MOVIES', 'status', status, 'imdbid', imdbid):
            return status
        else:
            logging.error('Could not set {} to {}'.format(imdbid, status))
            return False

    def get_stats(self):
        ''' Gets stats from database for graphing
        Formats data for use with Morris graphing library

        Returns dict
        '''

        stats = {}

        status = {'Waiting': 0,
                  'Wanted': 0,
                  'Found': 0,
                  'Snatched': 0,
                  'Finished': 0
                  }

        qualities = {'Default': 0}
        for i in core.CONFIG['Quality']['Profiles']:
            if i == 'Default':
                continue
            qualities[i] = 0

        years = {}
        added_dates = {}
        scores = {}

        movies = self.sql.get_user_movies()

        if not movies:
            return {'error', 'Unable to read database'}

        for movie in movies:
            if movie['status'] == 'Disabled':
                status['Finished'] += 1
            else:
                status[movie['status']] += 1

            if movie['quality'].startswith('{'):
                qualities['Default'] += 1
            else:
                if movie['quality'] not in qualities:
                    qualities[movie['quality']] = 1
                else:
                    qualities[movie['quality']] += 1

            if movie['year'] not in years:
                years[movie['year']] = 1
            else:
                years[movie['year']] += 1

            if movie['added_date'][:-3] not in added_dates:
                added_dates[movie['added_date'][:-3]] = 1
            else:
                added_dates[movie['added_date'][:-3]] += 1

            score = round((float(movie['score']) * 2)) / 2
            if score not in scores:
                scores[score] = 1
            else:
                scores[score] += 1

        stats['status'] = [{'label': k, 'value': v} for k, v in status.items()]
        stats['qualities'] = [{'label': k, 'value': v} for k, v in qualities.items()]
        stats['years'] = sorted([{'year': k, 'value': v} for k, v in years.items()], key=lambda k: k['year'])
        stats['added_dates'] = sorted([{'added_date': k, 'value': v} for k, v in added_dates.items() if v is not None], key=lambda k: k['added_date'])
        stats['scores'] = sorted([{'score': k, 'value': v} for k, v in scores.items()], key=lambda k: k['score'])

        return stats

    def estimate_size(self, human=True):
        movies = self.sql.get_user_movies()
        files = [i['finished_file'] for i in movies if i['finished_file'] is not None]

        size = 0

        for i in files:
            try:
                size += os.path.getsize(i)
            except Exception as e:
                logging.warning('Unable to get filesize for {}'.format(e), exc_info=True)

        if not human:
            return size
        else:
            return Conversions.human_file_size(size)


class Poster():

    def __init__(self):
        self.poster_folder = 'static/images/posters/'

        if not os.path.exists(self.poster_folder):
            os.makedirs(self.poster_folder)

    def save_poster(self, imdbid, poster_url):
        ''' Saves poster locally
        :param imdbid: str imdb identification number (tt123456)
        :param poster_url: str url of poster image

        Saves poster as watcher/static/images/posters/[imdbid].jpg

        Does not return.
        '''

        logging.info('Grabbing poster for {}.'.format(imdbid))

        new_poster_path = '{}{}.jpg'.format(self.poster_folder, imdbid)

        if os.path.exists(new_poster_path) is False:
            logging.info('Saving poster to {}'.format(new_poster_path))

            if poster_url == 'static/images/missing_poster.jpg':
                shutil.copy2(poster_url, new_poster_path)

            else:
                try:
                    poster_bytes = Url.open(poster_url, stream=True).content
                except (SystemExit, KeyboardInterrupt):
                    raise
                except Exception as e:
                    logging.error('Poster save_poster get', exc_info=True)

                try:
                    with open(new_poster_path, 'wb') as output:
                        output.write(poster_bytes)
                    del poster_bytes
                except (SystemExit, KeyboardInterrupt):
                    raise
                except Exception as e: # noqa
                    logging.error('Unable to save poster to disk.', exc_info=True)

            logging.info('Poster saved to {}'.format(new_poster_path))
        else:
            logging.warning('{} already exists.'.format(new_poster_path))

    def remove_poster(self, imdbid):
        ''' Deletes poster from disk.
        :param imdbid: str imdb identification number (tt123456)

        Does not return.
        '''

        logging.info('Removing poster for {}'.format(imdbid))
        path = '{}{}.jpg'.format(self.poster_folder, imdbid)
        if os.path.exists(path):
            os.remove(path)
        else:
            logging.warning('{} doesn\'t exist, cannot remove.'.format(path))
