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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

import urllib
import re

import xml.etree.cElementTree as etree

import sickbeard
import generic

from sickbeard.common import *
from sickbeard import logger
from sickbeard import tvcache, sceneHelpers

class EZRSSProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, "EZRSS")
        
        self.supportsBacklog = True

        self.cache = EZRSSCache(self)

        self.url = 'https://www.ezrss.it/'
        
        self.ezrss_ns = 'http://xmlns.ezrss.it/0.1/'

    def isEnabled(self):
        return sickbeard.EZRSS
        
    def imageName(self):
        return 'ezrss.gif'
      
    def getQuality(self, item):
        
        filename = item.findtext('{%s}torrent/{%s}fileName' %(self.ezrss_ns,self.ezrss_ns))
        quality = Quality.nameQuality(filename)
        if quality == Quality.UNKNOWN:
            # Use the filename in the torrent instead
            logger.log(u"Quality could not be found from the torrent name, checking actual filename", logger.MESSAGE)
            url = item.findtext('link').replace('&amp;','&')
            filename = self._extract_name_from_torrent(url)
            quality = Quality.nameQuality(filename)
        return quality

    def findSeasonResults(self, show, season):
        
        results = {}
        
        if show.is_air_by_date:
            logger.log(u"EZRSS doesn't support air-by-date backlog because of limitations on their RSS search.", logger.WARNING)
            return results
        
        results = generic.TorrentProvider.findSeasonResults(self, show, season)
        
        return results
    def _get_season_search_strings(self, show, season=None):
    
        params = {}
    
        if not show:
            return params
        
        params['show_name'] = sceneHelpers.sanitizeSceneName(show.name, ezrss=True).replace('.',' ').encode('utf-8')
          
        if season != None:
            params['season'] = season
    
        return [params]

    def _get_episode_search_strings(self, ep_obj):
    
        params = {}
        
        if not ep_obj:
            return params
                   
        params['show_name'] = sceneHelpers.sanitizeSceneName(ep_obj.show.name, ezrss=True).replace('.',' ').encode('utf-8')
        
        if ep_obj.show.is_air_by_date:
            params['date'] = str(ep_obj.airdate)
        else:
            params['season'] = ep_obj.season
            params['episode'] = ep_obj.episode
    
        return [params]

    def _doSearch(self, search_params, show=None):
    
        params = {"mode": "rss"}
    
        if search_params:
            params.update(search_params)
      
        searchURL = self.url + 'search/index.php?' + urllib.urlencode(params)

        logger.log(u"Search string: " + searchURL, logger.DEBUG)

        data = self.getURL(searchURL)

        if not data:
            return []
        
        try:
            responseSoup = etree.ElementTree(etree.XML(data))
            items = responseSoup.getiterator('item')
        except Exception, e:
            logger.log(u"Error trying to load EZRSS RSS feed: "+str(e).decode('utf-8'), logger.ERROR)
            logger.log(u"RSS data: "+data, logger.DEBUG)
            return []
        
        results = []

        for curItem in items:
            
            (title, url) = self._get_title_and_url(curItem)
            
            if not title or not url:
                logger.log(u"The XML returned from the EZRSS RSS feed is incomplete, this result is unusable: "+data, logger.ERROR)
                continue
    
            results.append(curItem)

        return results

    def _get_title_and_url(self, item):
        title = item.findtext('title')
        url = item.findtext('link').replace('&amp;','&')
        filename = item.findtext('{%s}torrent/{%s}fileName' %(self.ezrss_ns,self.ezrss_ns))
        
        new_title = self._extract_name_from_filename(filename)
        if new_title:
            title = new_title
            logger.log(u"Extracted the name "+title+" from the torrent link", logger.DEBUG)

        return (title, url)

    def _extract_name_from_filename(self, filename):
        name_regex = '(.*?)\.?(\[.*]|\d+\.TPB)\.torrent$'
        logger.log(u"Comparing "+name_regex+" against "+filename, logger.DEBUG)
        match = re.match(name_regex, filename, re.I)
        if match:
            return match.group(1)
        return None

    def _extract_name_from_torrent(self, url):
        contents = self.getURL(url)
        decoded = sceneHelpers.bdecode(contents)
        return decoded['info']['name']


class EZRSSCache(tvcache.TVCache):

    def __init__(self, provider):

        tvcache.TVCache.__init__(self, provider)

        # only poll EZRSS every 15 minutes max
        self.minTime = 15


    def _getRSSData(self):
        url = self.provider.url + 'feed/'

        logger.log(u"EZRSS cache update URL: "+ url, logger.DEBUG)

        data = self.provider.getURL(url)

        return data

    def _parseItem(self, item):

        title = item.findtext('title')
        url = item.findtext('link')
        filename = item.findtext('{%s}torrent/{%s}fileName' %(self.provider.ezrss_ns,self.provider.ezrss_ns))

        new_title = self.provider._extract_name_from_filename(filename)
        if new_title:
            title = new_title
            logger.log(u"Extracted the name "+title+" from the torrent link", logger.DEBUG)

        if not title or not url:
            logger.log(u"The XML returned from the EZRSS RSS feed is incomplete, this result is unusable", logger.ERROR)
            return

        logger.log(u"Adding item from RSS to cache: "+title, logger.DEBUG)

        self._addCacheEntry(title, url)

provider = EZRSSProvider()