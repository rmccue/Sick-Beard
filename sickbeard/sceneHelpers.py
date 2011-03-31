# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

from sickbeard.common import countryList
from sickbeard import logger
from sickbeard import db

import re
import datetime
import urllib

from name_parser.parser import NameParser, InvalidNameException

resultFilters = ("sub(pack|s|bed)", "nlsub(bed|s)?", "swesub(bed)?",
                 "(dir|sample|nfo)fix", "sample", "(dvd)?extras", 
                 "dub(bed)?", "german", "french", "core2hd")

def filterBadReleases(name):

    try:
        fp = NameParser()
        parse_result = fp.parse(name)
    except InvalidNameException:
        logger.log(u"Unable to parse the filename "+name+" into a valid episode", logger.WARNING)
        return False

    # if there's no info after the season info then assume it's fine
    if not parse_result.extra_info:
        return True

    # if any of the bad strings are in the name then say no
    for x in resultFilters:
        if re.search('(^|[\W_])'+x+'($|[\W_])', parse_result.extra_info, re.I):
            logger.log(u"Invalid scene release: "+name+" contains "+x+", ignoring it", logger.DEBUG)
            return False

    return True

def sanitizeSceneName (name, ezrss=False):
    if not ezrss:
        bad_chars = ",:()'!?"
    else:
        bad_chars = ",()'?"

    for x in bad_chars:
        name = name.replace(x, "")

    name = name.replace("- ", ".").replace(" ", ".").replace("&", "and").replace('/','.')
    name = re.sub("\.\.*", ".", name)

    if name.endswith('.'):
        name = name[:-1]

    return name

def sceneToNormalShowNames(name):

    if not name:
        return []

    name_list = [name]
    
    # use both and and &
    new_name = re.sub('(?i)([\. ])and([\. ])', '\\1&\\2', name, re.I)
    if new_name not in name_list:
        name_list.append(new_name)

    results = []

    for cur_name in name_list:
        # add brackets around the year
        results.append(re.sub('(\D)(\d{4})$', '\\1(\\2)', cur_name))
    
        # add brackets around the country
        country_match_str = '|'.join(countryList.values())
        results.append(re.sub('(?i)([. _-])('+country_match_str+')$', '\\1(\\2)', cur_name))

    results += name_list

    return list(set(results))

def makeSceneShowSearchStrings(show):

    showNames = allPossibleShowNames(show)

    # scenify the names
    return map(sanitizeSceneName, showNames)


def makeSceneSeasonSearchString (show, segment, extraSearchType=None):

    myDB = db.DBConnection()

    if show.is_air_by_date:
        numseasons = 0
        
        # the search string for air by date shows is just 
        seasonStrings = [segment]
    
    else:
        numseasonsSQlResult = myDB.select("SELECT COUNT(DISTINCT season) as numseasons FROM tv_episodes WHERE showid = ? and season != 0", [show.tvdbid])
        numseasons = int(numseasonsSQlResult[0][0])

        seasonStrings = ["S%02d" % segment]
        # since nzbmatrix allows more than one search per request we search SxEE results too
        if extraSearchType == "nzbmatrix":
            seasonStrings.append("%ix" % segment)

    showNames = set(makeSceneShowSearchStrings(show))

    toReturn = []
    term_list = []

    # search each show name
    for curShow in showNames:
        # most providers all work the same way
        if not extraSearchType:
            # if there's only one season then we can just use the show name straight up
            if numseasons == 1:
                toReturn.append(curShow)
            # for providers that don't allow multiple searches in one request we only search for Sxx style stuff
            else:
                for cur_season in seasonStrings:
                    toReturn.append(curShow + "." + cur_season)
        
        # nzbmatrix is special, we build a search string just for them
        elif extraSearchType == "nzbmatrix":
            if numseasons == 1:
                toReturn.append('"'+curShow+'"')
            elif numseasons == 0:
                toReturn.append('"'+curShow+' '+str(segment).replace('-',' ')+'"')
            else:
                term_list = [x+'*' for x in seasonStrings]
                if show.is_air_by_date:
                    term_list = ['"'+x+'"' for x in term_list]

                toReturn.append('"'+curShow+'"')
    
    if extraSearchType == "nzbmatrix":     
        toReturn = ['+('+','.join(toReturn)+')']
        if term_list:
            toReturn.append('+('+','.join(term_list)+')')
    return toReturn


def makeSceneSearchString (episode):

    myDB = db.DBConnection()
    numseasonsSQlResult = myDB.select("SELECT COUNT(DISTINCT season) as numseasons FROM tv_episodes WHERE showid = ? and season != 0", [episode.show.tvdbid])
    numseasons = int(numseasonsSQlResult[0][0])

    # see if we should use dates instead of episodes
    if episode.show.is_air_by_date and episode.airdate != datetime.date.fromordinal(1):
        epStrings = [str(episode.airdate)]
    else:
        epStrings = ["S%02iE%02i" % (int(episode.season), int(episode.episode)),
                    "%ix%02i" % (int(episode.season), int(episode.episode))]

    # for single-season shows just search for the show name
    if numseasons == 1:
        epStrings = ['']

    showNames = set(makeSceneShowSearchStrings(episode.show))

    toReturn = []

    for curShow in showNames:
        for curEpString in epStrings:
            toReturn.append(curShow + '.' + curEpString)

    return toReturn

def allPossibleShowNames(show):

    showNames = [show.name]
    showNames += [name for name in get_scene_exceptions(show.tvdbid)]

    # if we have a tvrage name then use it
    if show.tvrname != "" and show.tvrname != None:
        showNames.append(show.tvrname)

    newShowNames = []

    country_list = countryList
    country_list.update(dict(zip(countryList.values(), countryList.keys())))

    # if we have "Show Name Australia" or "Show Name (Australia)" this will add "Show Name (AU)" for
    # any countries defined in common.countryList
    # (and vice versa)
    for curName in set(showNames):
        if not curName:
            continue
        for curCountry in country_list:
            if curName.endswith(' '+curCountry):
                newShowNames.append(curName.replace(' '+curCountry, ' ('+country_list[curCountry]+')'))
            elif curName.endswith(' ('+curCountry+')'):
                newShowNames.append(curName.replace(' ('+curCountry+')', ' ('+country_list[curCountry]+')'))

    showNames += newShowNames

    return showNames

def isGoodResult(name, show, log=True):
    """
    Use an automatically-created regex to make sure the result actually is the show it claims to be
    """

    all_show_names = allPossibleShowNames(show)
    showNames = map(sanitizeSceneName, all_show_names) + all_show_names

    for curName in set(showNames):
        escaped_name = re.sub('\\\\[\\s.-]', '\W+', re.escape(curName))
        curRegex = '^' + escaped_name + '\W+(?:(?:S\d\d)|(?:\d\d?x)|(?:\d{4}\W\d\d\W\d\d)|(?:(?:part|pt)[\._ -]?(\d|[ivx]))|Season\W+\d+\W+|E\d+\W+)'
        if log:
            logger.log(u"Checking if show "+name+" matches " + curRegex, logger.DEBUG)

        match = re.search(curRegex, name, re.I)

        if match:
            logger.log(u"Matched "+curRegex+" to "+name, logger.DEBUG)
            return True

    if log:
        logger.log(u"Provider gave result "+name+" but that doesn't seem like a valid result for "+show.name+" so I'm ignoring it")
    return False

def get_scene_exceptions(tvdb_id):
    """
    Given a tvdb_id, return a list of all the scene exceptions.
    """

    myDB = db.DBConnection("cache.db")
    exceptions = myDB.select("SELECT show_name FROM scene_exceptions WHERE tvdb_id = ?", [tvdb_id])
    return [cur_exception["show_name"] for cur_exception in exceptions]

def get_scene_exception_by_name(show_name):
    """
    Given a show name, return the tvdbid of the exception, None if no exception
    is present.
    """

    myDB = db.DBConnection("cache.db")
    
    # try the obvious case first
    exception_result = myDB.select("SELECT tvdb_id FROM scene_exceptions WHERE LOWER(show_name) = ?", [show_name.lower()])
    if exception_result:
        return int(exception_result[0]["tvdb_id"])

    all_exception_results = myDB.select("SELECT show_name, tvdb_id FROM scene_exceptions")
    for cur_exception in all_exception_results:

        cur_exception_name = cur_exception["show_name"]
        cur_tvdb_id = int(cur_exception["tvdb_id"])

        if show_name.lower() in (cur_exception_name.lower(), sanitizeSceneName(cur_exception_name).lower().replace('.',' ')):
            logger.log(u"Scene exception lookup got tvdb id "+str(cur_tvdb_id)+u", using that", logger.DEBUG)
            return cur_tvdb_id

    return None

def retrieve_exceptions():

    exception_dict = {}

    url = 'http://midgetspy.github.com/sb_tvdb_scene_exceptions/exceptions.txt'
    open_url = urllib.urlopen(url)
    
    # each exception is on one line with the format tvdb_id: 'show name 1', 'show name 2', etc
    for cur_line in open_url.readlines():
        tvdb_id, sep, aliases = cur_line.partition(':')
        
        if not aliases:
            continue
    
        tvdb_id = int(tvdb_id)
        
        # regex out the list of shows, taking \' into account
        alias_list = [re.sub(r'\\(.)', r'\1', x) for x in re.findall(r"'(.*?)(?<!\\)',?", aliases)]
        
        exception_dict[tvdb_id] = alias_list

    myDB = db.DBConnection("cache.db")
    myDB.action("DELETE FROM scene_exceptions WHERE 1=1")
    
    for cur_tvdb_id in exception_dict:
        for cur_exception in exception_dict[cur_tvdb_id]:
            myDB.action("INSERT INTO scene_exceptions (tvdb_id, show_name) VALUES (?,?)", [cur_tvdb_id, cur_exception])


# The following decoder is licensed under the MIT license:
#
# Copyright (c) 2010 Pedro Rodrigues
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

class BDecoder:
    @staticmethod
    def _decode_integer(input):
        end = input.find('e')
        if end>-1:
            return (int(input[1:end]),input[end+1:])
            end += 1
        else:
            raise ValueError("Missing ending delimiter 'e'")

    @staticmethod
    def _decode_string(input):
        start = input.find(':')+1
        size = int(input[:start-1])
        end = start+size
        return (input[start:end], input[end:])

    @staticmethod
    def _decode_list(input):
        result = []
        remainder = input[1:]
        while True:
            if remainder[0] == 'i':
                r = BDecoder._decode_integer(remainder)
                result.append(r[0])
                remainder = r[1]

            elif remainder[0].isdigit():
                r = BDecoder._decode_string(remainder)
                result.append(r[0])
                remainder = r[1]

            elif remainder[0] == 'l':
                r = BDecoder._decode_list(remainder)
                result.append(r[0])
                remainder = r[1]

            elif remainder[0] == 'd':
                r = BDecoder._decode_dict(remainder)
                result.append(r[0])
                remainder = r[1]

            elif remainder[0] == 'e':
                remainder = remainder[1:]
                break

            else:
                raise ValueError("Invalid initial delimiter '%r' found while decoding a list" % remainder[0])

        return (result,remainder)

    @staticmethod
    def _decode_dict(input):
        result = {}
        remainder = input[1:]
        while remainder[0] != 'e':
            r = BDecoder._decode_string(remainder)
            key = r[0]
            remainder = r[1]

            if remainder[0] == 'i':
                r = BDecoder._decode_integer(remainder)
                value = r[0]
                result[key] = value
                remainder = r[1]

            elif remainder[0].isdigit():
                r = BDecoder._decode_string(remainder)
                value = r[0]
                result[key] = value
                remainder = r[1]

            elif remainder[0] == 'l':
                r = BDecoder._decode_list(remainder)
                value = r[0]
                result[key] = value
                remainder = r[1]

            elif remainder[0] == 'd':
                r = BDecoder._decode_dict(remainder)
                value = r[0]
                result[key] = value
                remainder = r[1]

            else:
                raise ValueError("Invalid initial delimiter '%r' found while decoding a dictionary" % remainder[0])

        return (result,remainder[1:])

def bdecode(input):
    '''Decode strings from bencode format to python value types.

    Keyword arguments:
    input -- the input string to be decoded
    '''

    input = input.strip()

    if input[0] == 'i':
        return BDecoder._decode_integer(input)[0]

    elif input[0].isdigit():
        return BDecoder._decode_string(input)[0]

    elif input[0] == 'l':
        return BDecoder._decode_list(input)[0]

    elif input[0] == 'd':
        return BDecoder._decode_dict(input)[0]
    else:
        raise ValueError("Invalid initial delimiter '%s'" % input[0])
