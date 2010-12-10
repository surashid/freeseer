#!/usr/bin/python
# -*- coding: utf-8 -*-

# freeseer - vga/presentation capture software
#
#  Copyright (C) 2010  Free and Open Source Software Learning Centre
#  http://fosslc.org
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

# For support, questions, suggestions or any other inquiries, visit:
# http://wiki.github.com/fosslc/freeseer/


import codecs
import datetime
import time
import logging
import logging.config
import os

from freeseer.backend.gstreamer import *

from config import Config
from logger import Logger
from db_connector import *
from rss_parser import *
from presentation import *

__version__=u'1.9.7'

class FreeseerCore:
    '''
    Freeseer core logic code.  Used to link a GUI frontend with a recording
    backend such as backend.gstreamer
    '''
    def __init__(self, ui):
        self.ui = ui
        
        # Read in config information
        configdir = os.path.abspath(os.path.expanduser('~/.freeseer/'))
        self.config = Config(configdir)
        self.logger = Logger(configdir)
        self.db = DB_Connector(configdir)

        # Start Freeseer Recording Backend
        self.backend = Freeseer_gstreamer(self)
        resolution = self.config.resolution.split('x')
        self.change_output_resolution(resolution[0], resolution[1])

        self.feedback = False
        self.spaces = False
      
        self.logger.log.info(u"Core initialized")   
	
    def duplicate_exists(self, recordname):
	'''
	Checks to see if a record name already exists in the directory.
	'''
	filename = self.config.videodir + '/' + recordname
	try:
		result = open(filename, 'r')
	except IOError:
		return False
	return True

    def get_record_name(self, presentation):
        '''
        Returns the filename to use when recording.
        '''
        recordname = self.make_record_name(presentation)

	count = 0
	tempname = recordname
	# check if this record name already exists in this directory and add "-NN" ending if so.
	while(self.duplicate_exists(tempname + ".ogg")):
	    tempname = recordname + "-" + self.make_id_from_string(count, "0123456789")
	    count+=1
	
	recordname = tempname + ".ogg"
        self.logger.log.debug('Set record name to ' + recordname)        
	return recordname

    def make_record_name(self, presentation):
        '''
        Create an 'EVENT-TITLE-UNIQUE' record name
        '''	
	event = self.make_shortname(presentation.event)
	title = self.make_shortname(presentation.title)
	unique = self.make_id_from_string(presentation.filename_id)
 
	if(event == ""):
		return title+"-"+unique

	return event+"-"+title+"-"+unique

    def make_id_from_string(self, position, string='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
       	'''
	Returns an "NN" id given an integer and a string of valid characters for the id
	('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ' are the valid characters for UNIQUE in a record name)
	'''	
	index1 = position % string.__len__()
	index0 = int( position / string.__len__() )

	if(index0 >= string.__len__() ):
		self.logger.log.debug('WARNING: Unable to generate unique filename.')
		# Return a unique 2 character string which will not overwrite previous files.
		# There is a possibility of infinite looping on testing duplicates once
		# all possible UNIQUE's and NN's are exhausted if all the files are kept 
		# in the same directory.
		# (36 * 36 * 100 filenames before this occurs, assuming EVENT is unique inside the directory.)
		return "##" 

	return string[index0]+string[index1]

    def make_shortname(self, string):
	'''
	Returns the first four characters of a string, excluding spaces.
	'''
	string = string.replace(" ", "")
	return string[0:4].upper()

    ##
    ## Database Functions
    ##
    def get_talk_titles(self):
        return self.db.get_talk_titles()
        
    def get_talk_rooms(self):
        return self.db.get_talk_rooms()
    
    def get_talk_events(self):
        return self.db.get_talk_events()

    def filter_talks_by_event_room(self, event, room):
        return self.db.filter_talks_by_event_room(event, room)

    def get_presentation_id_by_selected_title(self, title):
    	'''
    	Obtains a presentation ID given a title string from the GUI
    	'''
	# Run a database query as if we have selected "All" Events "All" Rooms,
        # and check the index of the title string in this list, this corresponds
	# to the presentation id in the database. (If we add 1 to this index)
	# NOTE: This method of obtaining the presentation id relies on the GUI
	#	using the method: filter_talks_by_event_room() to populate it's 
	#	talk list, since we are comparing strings created by this method.
	talkTitles = self.db.filter_talks_by_event_room("All", "All")
	return talkTitles.index(title) + 1
	
    def get_presentation(self, presentation_id):
	return self.db.get_presentation(presentation_id)

    def add_talks_from_rss(self, rss):
        entry = str(rss)
        feedparser = FeedParser(entry)

        if len(feedparser.build_data_dictionary()) == 0:
            self.logger.log.info("RSS: No data found.")

        else:
            for presentation in feedparser.build_data_dictionary():
                talk = Presentation(presentation["Title"],
                                    presentation["Speaker"],
                                    "",
                                    presentation["Level"],
                                    presentation["Event"],
                                    presentation["Time"],
                                    presentation["Room"])
                                    
                if not self.db.db_contains(talk):
                    self.add_talk(talk)

    def get_presentation_id(self, presentation):
        talk_id = self.db.get_presentation_id(presentation)
        self.logger.log.debug('Found presentation id for %s - %s. ID: %s',
                                presentation.speaker,
                                presentation.title,
                                talk_id)
        return talk_id

    def add_talk(self, presentation):
        self.db.add_talk(presentation)
        self.logger.log.debug('Talk added: %s - %s', presentation.speaker, presentation.title)
        
    def update_talk(self, talk_id, speaker, title, room):
        self.db.update_talk(talk_id, speaker, title, room)
        self.logger.log.debug('Talk updated: %s - %s', speaker, title)
        
    def delete_talk(self, talk_id):
        self.db.delete_talk(talk_id)
        self.logger.log.debug('Talk deleted: %s', talk_id)

    def clear_database(self):
        self.db.clear_database()
        self.logger.log.debug('Database cleared!')

    ##
    ## Backend Functions
    ##
    def get_video_sources(self):
        '''
        Returns supported video sources.
        '''
        vidsrcs = self.backend.get_video_sources()
        self.logger.log.debug('Available video sources: ' + str(vidsrcs))
        return vidsrcs
        
    def get_video_devices(self, device_type):
        '''
        Returns available video devices.
        '''
        viddevs = self.backend.get_video_devices(device_type)
        self.logger.log.debug('Available video devices for ' + device_type + ': ' + str(viddevs))
        return viddevs
    
    def get_audio_sources(self):
        '''
        Returns supported audio sources.
        '''
        sndsrcs = self.backend.get_audio_sources()
        self.logger.log.debug('Available audio sources: ' + str(sndsrcs))
        return sndsrcs

    def set_video_mode(self, mode):
        '''
        Enables video recording when mode is set to True
        Disables video recording when mode is set to False
        '''
        if mode == True:
            self.logger.log.info('Video recording: ENABLED')
        else:
            self.logger.log.info('Video recording: DISABLED')
            
        self.backend.set_video_mode(mode)
        
    def change_videosrc(self, vid_source, vid_device):
        '''
        Informs backend of new video source to use when recording.
        '''
        self.backend.change_video_source(vid_source, vid_device)
        self.logger.log.debug('Video source changed to ' + vid_source + ' using ' + vid_device)

    def set_record_area(self, enabled):
        self.backend.set_record_area(enabled)

    def set_recording_area(self, x1, y1, x2, y2):
        # gstreamer backend needs to have the lower x/y coordinates
        # sent first.
        if (x2 < x1):
            if (y2 < y1):
                self.backend.set_recording_area(x2, y2, x1, y1)
            else:
                self.backend.set_recording_area(x2, y1, x1, y2)
        else:
            if (y2 < y1):
                self.backend.set_recording_area(x1, y2, x2, y1)
            else:
                self.backend.set_recording_area(x1, y1, x2, y2)

    def change_output_resolution(self, width, height):
        self.backend.change_output_resolution(width, height)
        self.logger.log.debug('Video output resolution changed to ' + width + 'x' + height)

    def set_audio_mode(self, mode):
        '''
        Enables video recording when mode is set to True
        Disables video recording when mode is set to False
        '''
        if mode == True:
            self.logger.log.info('Audio recording: ENABLED')
        else:
            self.logger.log.info('Audio recording: DISABLED')

        self.backend.set_audio_mode(mode)

    def change_soundsrc(self, snd_source):
        '''
        Informs backend of new audio source to use when recording.
        '''
        return self.backend.change_audio_source(snd_source)

    def test_sources(self, state, video=False, audio=False):
        if state == True:
            self.backend.test_feedback_start(video, audio)
        else:
            self.backend.test_feedback_stop()

    def prepare_metadata(self, presentation):
	'''
	Returns a dictionary of tags and tag values to be used
	to populate the current recording's file metadata.
	'''
	return { "title" : presentation.title,
		 "artist" : presentation.speaker,
		 "performer" : presentation.speaker,
		 "album" : presentation.event,
		 "location" : presentation.room,
		 "date" : str(datetime.date.today()),
		 "comment" : presentation.description}

    def record(self, presentation):
        '''
        Informs backend to begin recording presentation.
        '''
	
	#create a filename to record to
        record_name = self.get_record_name(presentation)

	#prepare metadata
	data = self.prepare_metadata(presentation)
	self.backend.populate_metadata(data)

        record_location = os.path.abspath(self.config.videodir + '/' + record_name)
        self.backend.record(record_location)
        self.logger.log.info('Recording started')

    def stop(self):
        '''
        Informs backend to stop recording.
        '''
        self.backend.stop()
        self.logger.log.info('Recording stopped')

    def test_feedback(self, video, audio):
        if self.feedback:
            self.feedback = False
            self.backend.test_feedback_stop()
        else:
            self.feedback = True
            self.backend.test_feedback_start(video, audio)
            
    def preview(self, enable=False, window_id=None):
        '''
        Enable/Disable the video preview window.
        '''
        if enable == True:
            self.backend.enable_video_feedback(window_id)
            self.logger.log.info('Video Preview Activated')
        else:
            self.backend.disable_video_feedback()
            self.logger.log.info('Video Preview Deactivated')

    def audioFeedback(self, enable=False):
        '''
        Enable/Disable the audio preview.
        '''
        if enable == True:
            self.backend.enable_audio_feedback()
            self.logger.log.info('Audio Feedback Activated')
	else:
            self.backend.disable_audio_feedback()
            self.logger.log.info('Audio Feedback Deactivated')

    def audioFeedbackEvent(self, percent):
        event_type = 'audio_feedback'
        self.ui.coreEvent(event_type, percent)
