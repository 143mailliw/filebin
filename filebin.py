#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import sys
import math
import time
import json
import magic
import fcntl
import select
import shutil
import random
import hashlib
import pymongo
import datetime
import tempfile
import mimetypes
import string

import PythonMagick
import pyexiv2

import subprocess
#from tornado.database import Connection

import flask
import werkzeug

logfile = "/var/log/app/filebin/filebin.log"
file_directory = "/var/www/includes/filebin/files"
temp_directory = "/var/www/includes/filebin/temp"
thumbnail_directory = "/var/www/includes/filebin/thumbnails"
failure_sleep = 3

dbhost = "127.0.0.1"
dbport = 27017
db = "filebin"

thumbnail_width = 260
thumbnail_height = 180

app = flask.Flask(__name__)
app.config.from_object(__name__)

# Generate tag
def generate_tag():
    chars = string.ascii_lowercase + string.digits
    length = 10
    return ''.join(random.choice(chars) for _ in xrange(length))

# Generate passphrase
def generate_key():
    chars = string.ascii_letters + string.digits
    length = 30
    return ''.join(random.choice(chars) for _ in xrange(length))

# Generate path to save the file
def get_path(tag = False, filename = False, thumbnail = False):

    # Use two levels of directories, just for, eh, scalability
    m = re.match('^(.)(.)',tag)
    a = m.group(1)
    b = m.group(2)

    if thumbnail == True:
        path = '%s/%s/%s/%s' % (thumbnail_directory,a,b,tag)

        if filename:
            #path = '%s/%s-thumb.jpg' % (path,filename)
            path = '%s/%s' % (path,filename)

    else:
        path = '%s/%s/%s/%s' % (file_directory,a,b,tag)

        if filename:
            path = '%s/%s' % (path,filename)

    return str(path)

# Function to calculate the md5 checksum for a file on the local file system
def md5_for_file(target):
    md5 = hashlib.md5()
    with open(target,'rb') as f: 
        for chunk in iter(lambda: f.read(128*md5.block_size), b''): 
            md5.update(chunk)

    f.close()
    return md5.hexdigest()

# A simple log function. Might want to inject to database and/or syslog instead
def log(priority,text):
    try:
        f = open(logfile, 'a')

    except:
        pass

    else:
        time = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if f:
            f.write("%s %s : %s\n" % (time, priority, text))
            f.close()

# Input validation
# Verify the flask.request. Return True if the flask.request is OK, False if it isn't.
def verify(tag = False, filename = False):
    if tag:
        # We want to have a long tag
        if len(tag) < 10:
            return False

        # Only known chars are allowed in the tag
        if len(tag) >= 10 and len(tag) < 100:
            m = re.match('^[a-zA-Z0-9]+$',tag)
            if not m:
                return False

    if filename:
        # Only known chars are allowed in the filename
        if not re.match('^[a-zA-Z0-9\.\-\_\%()\ ]+$',filename):
            return False

        # '..' is not allowed
        if re.search('\.\.',filename):
            return False

        # We want to have a valid filename
        if len(filename) < 1:
            return False

    return True

def get_tags():
    tags = []

    col = dbopen('tags')
    try:
        cursor = col.find()

    except:
        cursor = False

    if cursor:
        for t in cursor:
            tags.append(t['_id'])

    return tags

def get_public_tags():
    tags = []

    col = dbopen('tags')
    try:
        cursor = col.find({'expose' : 'public'})

    except:
        cursor = False

    if cursor:
        for t in cursor:
            tags.append(t['_id'])

    return tags

def get_files_in_tag(tag, page = False, per_page = 100):
    files = []

    if not verify(tag):
        return files

    conf = read_tag_configuration(tag)

    col = dbopen('files')
    try:
        if page == False:
            cursor = col.find({'tag' : tag}).sort('captured', 1)
        else:
            skip = (int(page)-1) * per_page
            cursor = col.find({'tag' : tag},skip = skip, limit = per_page).sort('captured', 1)

    except:
        cursor = False

    if cursor:
        for f in cursor:
            filename = f['filename']
            i = {}
            i['filename'] = f['filename']
            i['downloads'] = f['downloads']
            i['mimetype'] = f['mimetype']
            i['filepath'] = f['filepath']
            i['size'] = "%.2f" % (f['size'] / 1024 / round(1024))
            i['bandwidth'] = "%.2f" % ((f['downloads'] * f['size']) / 1024 / round(1024))
            i['uploaded'] = f['uploaded']
            i['uploaded_iso'] = datetime.datetime.strptime(str(f['uploaded']), \
                                    "%Y%m%d%H%M%S")

            # Add thumbnail path if the tag should show thumbnails and the
            # thumbnail for this filename exists.
            if conf['preview'] == 'on':
                thumbfile = get_path(tag,filename,True)
                if os.path.exists(thumbfile):
                    i['thumbnail'] = True

            #files[filename] = i 
            files.append(i)

    return files

def get_header(header):
    value = False

    if os.environ:
        m = re.compile('%s$' % header, re.IGNORECASE)
        header = string.replace(header,'-','_')
        for h in os.environ:
            if m.search(h):
                 value = os.environ[h]

    if not value:
        try:
            value = flask.request.headers.get(header)

        except:
            pass
       
    if value:
        log("DEBUG","Header %s = %s" % (header,value))
    else:
        log("DEBUG","Header %s was NOT FOUND" % (header))

    return value

# Detect the client address here
def get_client():
    client = False

    try:
        client = os.environ['HTTP_X_FORWARDED_FOR']

    except:
        try:
            client = os.environ['REMOTE_ADDR']
 
        except:
            client = False

    return client

def dbopen(collection):
    # Connect to mongodb
    try:
        connection = pymongo.Connection(dbhost,dbport)

    except:
        log("ERROR","Unable to connect to database server " \
            "at %s:%s" % (dbhost,dbport))
        return False

    # Select database
    try:
        database = connection[db]

    except:
        log("ERROR","Unable to select to database %s " \
            "at %s:%s" % (db,dbhost,dbport))
        return False

    # Select collection
    try:
        col = database[collection]

    except:
        log("ERROR","Unable to select to collection %s " \
            "in database at %s:%s" % (collection,db,dbhost,dbport))
        return False

    # Return collection handler
    return col

def authenticate_key(tag,key):
    col = dbopen('tags')
    try:
        configuration = col.find_one({'_id' : tag, 'key' : key})

    except:
        return False

    if configuration:
        return True

    return False 

def read_tag_creation_time(tag):
    col = dbopen('tags')
    try:
        t = col.find_one({'_id' : tag})

    except:
        return False

    try:
        t['registered']

    except:
        return False

    else:
        return t['registered']

    return False 

def generate_thumbnails(tag):
    conf = read_tag_configuration(tag)

    if not conf['preview'] == 'on':
        return True

    thumbnail_dir = get_path(tag, thumbnail = True)
    if not os.path.exists(thumbnail_dir):
        os.makedirs(thumbnail_dir)
        if not os.path.exists(thumbnail_dir):
            log("ERROR","Unable to create directory %s for tag %s" % \
                (thumbnail_dir,tag))
            return False

    files = get_files_in_tag(tag)
    m = re.compile('^image/(jpeg|jpg|png|gif)')
    for f in files:
        filename = f['filename']

        try:
            mimetype = f['mimetype']

        except:
            log("DEBUG","Unable to read mimetype for tag %s, filename %s" \
                % (tag, filename))

        else:
            if m.match(mimetype):
                # Decide the name of the files here
                thumbfile = get_path(tag,filename,True)
                filepath = get_path(tag,filename)


                # TODO: Should also check if filepath is newer than thumbfile!
                if not os.path.exists(thumbfile):
                    log("DEBUG","Create thumbnail (%s) of file (%s)" \
                        % (thumbfile,filepath))

                    try:
                        im = PythonMagick.Image(filepath)
                        im.scale('%dx%d' % (int(thumbnail_width),int(thumbnail_height)))
                        im.write(str(thumbfile))

                    except:
                        log("ERROR","Unable to generate thumbnail for file " \
                            "%s in tag %s with mimetype %s" \
                            % (filename,tag,mimetype))
                    
                    else:
                        log("INFO","Generated thumbnail for file %s " \
                            "in tag %s with mimetype %s" \
                            % (filename,tag,mimetype))

def get_tag_lifetime(tag):
    conf = read_tag_configuration(tag)

    registered = datetime.datetime.strptime(str(conf['registered']), \
                                            "%Y%m%d%H%M%S")
    now = datetime.datetime.utcnow()
    ttl = int(conf['ttl'])
    if ttl == 0:
        # Expire immediately
        to = now

    elif ttl == 1:
        # One week from registered
        to = registered + datetime.timedelta(weeks = 1)
        
    elif ttl == 2:
        # One month from registered
        to = registered + datetime.timedelta(weeks = 4)

    elif ttl == 3:
        # Six months from registered
        to = registered + datetime.timedelta(weeks = 26)

    elif ttl == 4:
        # One year from registered
        to = registered + datetime.timedelta(weeks = 52)

    elif ttl == 5:
        # Forever
        to = now + datetime.timedelta(weeks = 52)

    if int(to.strftime("%Y%m%d%H%M%S")) > int(now.strftime("%Y%m%d%H%M%S")):
        # TTL not reached
        return True

    else:
        # Tag should be removed
        # TTL reached
        return False

def read_tag_log(tag):
    ret = []
    col = dbopen('log')
    try:
        entries = col.find({'tag' : tag}).sort('time',-1)

    except:
        return ret

    try:
        entries

    except:
        return ret

    else:
        for entry in entries:
           l = {}
           l['client']    = entry['client']     
           l['time']      = datetime.datetime.strptime(str(entry['time']),"%Y%m%d%H%M%S")
           #l['time']      = entry['time']
           l['filename']  = entry['filename']     
           l['direction'] = entry['direction']     
           ret.append(l)

    return ret 

def read_tag_configuration(tag):
    col = dbopen('tags')
    try:
        configuration = col.find_one({'_id' : tag})

    except:
        return False

    try:
        configuration

    except:
        return False

    else:
        return configuration

    return False 

def hash_key(key):
    # Let's hash the admin key
    m = hashlib.sha512()
    m.update(key)
    return m.hexdigest()

def add_file_to_database(i):
    status = False

    now = datetime.datetime.utcnow()
    i['downloads'] = 0
    i['uploaded']  = now.strftime("%Y%m%d%H%M%S")

    col = dbopen('files')
    try:
        col.update({
                     'tag'         : i['tag'],
                     'filename'    : i['filename']
                   },
                   i,
                   True)

    except:
        log("ERROR","Unable to add file %s in tag %s to database" \
            % (i['filename'],i['tag']))

    else:
        status = True
    return status

def create_default_tag_configuration(tag,key):
    now = datetime.datetime.utcnow()
    status = False

    hashed_key = hash_key(key)

    col = dbopen('tags')
    try:
        col.update({'_id'          : tag},
                   {
                     '_id'         : tag,
                     'key'         : hashed_key,
                     'ttl'         : 3,
                     'expose'      : 'private',
                     'permission'  : 'rw',
                     'preview'     : 'on',
                     'registered'  : now.strftime("%Y%m%d%H%M%S")
                   },
                   True)

    except:
        log("ERROR","Unable to create default configuration for " \
            "tag %s." % (tag))

    else:
        status = True

    return status

def verify_admin_request(req):
    try:
        ttl = int(req.form['ttl'])
        expose = req.form['expose']
        preview = req.form['preview']
        permission = req.form['permission']

    except:
        return False

    if ttl < 0 or ttl > 5:
        return False

    if expose != 'private' and expose != 'public':
        return False

    if preview != 'on' and preview != 'off':
        return False

    if permission != 'ro' and permission != 'rw':
        return False

    return True

# Increment download counter
def increment_download_counter(tag,filename):
    col = dbopen('files')
    try:
        col.update({
                     'tag'         : tag,
                     'filename'    : filename
                   },
                   {
                     '$inc' : {
                       'downloads' : 1
                     }
                   },
                   True)
    
    except:
        log("ERROR","Unable to increment download counter for " \
            "%s in %s" % (filename,tag))

def dblog(client,tag,filename,direction):
    time = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    col = dbopen('log')
    try:
        col.insert({
                     'time'        : time,
                     'client'      : client,
                     'tag'         : tag,
                     'filename'    : filename,
                     'direction'   : direction
                   })
                   
    
    except:
        log("ERROR","Unable to log %s of file %s to tag %s and client %s" \
            % (direction,filename,tag,client))

def get_mimetype(path):
    m = magic.open(magic.MAGIC_MIME_TYPE)
    m.load()
    mimetype = m.file(path)
    return mimetype

def get_time_of_capture(path):
    ret = False
    try:
        image = pyexiv2.Image(path)
        image.readMetadata()
        time = str(image['Exif.Image.DateTime'])

    except:
        log("ERROR","EXIF: Unable to extract DateTime from %s" % (path))

    else:
        log("DEBUG","EXIF: DateTime = %s for %s" % (time,path))
        try:
            time_dt = pyexiv2.StringToDateTime(time)

        except:
            log("ERROR","EXIF: Unable to convert DateTime from string to " \
                "datetime")
            ret = time

        else:
            ret = time_dt

    return ret

def remove_tag(tag):
    status = True

    # Remove from the database
    col = dbopen('tags')
    try:
        col.remove({'_id' : tag})

    except:
        log("ERROR","%s: Unable to remove tag from mongodb/tags" % (tag))
        status = False

    else:
        log("INFO","%s: Removed tag from mongodb/tags" % (tag))

    col = dbopen('files')
    try:
        col.remove({'tag' : tag})

    except:
        log("ERROR","%s: Unable to remove tag from mongodb/files" % (tag))
        status = False

    else:
        log("INFO","%s: Removed tag from mongodb/files" % (tag))

    thumbdir = get_path(tag,thumbnail = True)
    if os.path.exists(thumbdir):
        try:
            shutil.rmtree(thumbdir)

        except:
            log("ERROR","%s: Unable to remove thumbnail files (%s)" % \
                (tag,thumbdir))
            status = False

        else:
            log("INFO","%s: Removed thumbnail files (%s) for tag" % \
                (tag,thumbdir))

    else:
        log("INFO","%s: Thumbnail directory (%s) does not exist" % \
            (tag,thumbdir))

    filedir = get_path(tag)
    if os.path.exists(filedir):
        try:
            shutil.rmtree(filedir)

        except:
            log("ERROR","%s: Unable to remove files (%s)" % (tag,filedir))
            status = False

        else:
            log("INFO","%s: Removed files (%s) for tag" % (tag,filedir))

    return status

@app.route("/")
def index():
    return flask.render_template("index.html", title = "Online storage at your fingertips")

@app.route("/<tag>/")
@app.route("/<tag>")
def tag(tag):
    return flask.redirect('/%s/page/1' % (tag))

@app.route("/<tag>/page/<page>/")
@app.route("/<tag>/page/<page>")
def tag_page(tag,page):
    files = {}

    if not verify(tag):
        time.sleep(failure_sleep)
        flask.abort(400)

    conf = read_tag_configuration(tag)

    num_files = len(get_files_in_tag(tag))

    per_page = 50
    pages = int(math.ceil(num_files / round(per_page)))

    # Input validation
    try:
        int(page)
 
    except:
       flask.abort(400)

    page = int(page)
    if page < 1:
        page = 1

    if page > pages:
        page = pages

    #log("DEBUG","PAGES: Tag %s has %d files, which will be presented in %d pages with %d files per page" % (tag, num_files, pages, per_page))
    files = get_files_in_tag(tag,page,per_page)

    return flask.render_template("tag.html", tag = tag, files = files, conf = conf, num_files = num_files, pages = pages, page = page, title = "Tag %s" % (tag))

@app.route("/<tag>/json/")
@app.route("/<tag>/json")
def tag_json(tag):
    files = {}

    if not verify(tag):
        time.sleep(failure_sleep)
        flask.abort(400)

    conf = read_tag_configuration(tag)
    files = get_files_in_tag(tag)

    for f in files:
        # Remove some unecessary stuff
        del(f['filepath'])
        del(f['uploaded_iso'])

    # Verify json format
    try:
        ret = json.dumps(files, indent=2)

    except:
        flask.abort(501)

    #h = werkzeug.Headers()
    #h.add('Content-Disposition', 'inline' % (tag))
    return flask.Response(ret, mimetype='text/json')

@app.route("/thumbnails/<tag>/<filename>")
def thumbnail(tag,filename):
    if verify(tag,filename):
        filepath = get_path(tag,filename,True)
        #log("DEBUG","Deliver thumbnail from %s" % (filepath))
        if os.path.isfile(filepath):
            # Output image files directly to the client browser
            return flask.send_file(filepath)

    flask.abort(404)

@app.route("/<tag>/file/<filename>")
def file(tag,filename):

    client = get_client()
    mimetype = False
    if verify(tag,filename):
        log_prefix = "%s/%s -> %s" % (tag,filename,client)
        file_path = get_path(tag,filename)
        if os.path.isfile(file_path):
            mimetype = get_mimetype(file_path)

            # Increment download counter
            increment_download_counter(tag,filename)

            # Log the activity
            dblog(client,tag,filename,'download')

            # Output image files directly to the client browser
            m = re.match('^image|^video|^audio|^text/plain|^application/pdf',mimetype)
            if m:
                log("INFO","%s: Delivering file (%s)" % (log_prefix,mimetype))
                return flask.send_file(file_path)

            # Output rest of the files as attachments
            log("INFO","%s: Delivering file (%s) as " \
                "attachement." % (log_prefix,mimetype))

            return flask.send_file(file_path, as_attachment = True)

    flask.abort(404)

@app.route("/log/<tag>/<key>/")
@app.route("/log/<tag>/<key>")
def admin_log(tag,key):
    if not verify(tag):
        flask.abort(400)

    # Let's hash the admin key
    hashed_key = hash_key(key)

    if not authenticate_key(tag,hashed_key):
        flask.abort(401)

    log = read_tag_log(tag)
    conf = read_tag_configuration(tag)

    return flask.render_template("log.html", tag = tag, log = log, conf = conf, key = key, title = "Log entries for %s" % (tag))

@app.route("/admin/<tag>/<key>/", methods = ['POST', 'GET'])
@app.route("/admin/<tag>/<key>", methods = ['POST', 'GET'])
def admin(tag,key):
    if not verify(tag):
        flask.abort(400)

    # Let's hash the admin key
    hashed_key = hash_key(key)

    if not authenticate_key(tag,hashed_key):
        time.sleep(failure_sleep)
        flask.abort(401)

    ttl_iso = {}
    # When the tag was created (YYYYMMDDhhmmss UTC)
    registered = read_tag_creation_time(tag)
    
    try:
        registered_iso = datetime.datetime.strptime(str(registered),"%Y%m%d%H%M%S")

    except:
        registered_iso = "N/A"

    else:
        ttl_iso['oneweek']  = (registered_iso + datetime.timedelta(7)).strftime("%Y-%m-%d")
        ttl_iso['onemonth'] = (registered_iso + datetime.timedelta(30)).strftime("%Y-%m-%d")
        ttl_iso['sixmonths'] = (registered_iso + datetime.timedelta(182)).strftime("%Y-%m-%d")
        ttl_iso['oneyear']  = (registered_iso + datetime.timedelta(365)).strftime("%Y-%m-%d")

    if flask.request.method == 'POST':
        if not verify_admin_request(flask.request):
            time.sleep(failure_sleep)
            flask.abort(400)

        ttl        = int(flask.request.form['ttl'])
        expose     = flask.request.form['expose']
        permission = flask.request.form['permission']
        preview    = flask.request.form['preview']

        col = dbopen('tags')
        try:
            col.update({'_id' : tag},
                       {
                         '$set' : {
                           'ttl' : ttl,
                           'expose' : expose,
                           'permission' : permission,
                           'preview' : preview
                         }
                       },
                       False)

        except:
            log("ERROR","Unable to update configuration for " \
                "tag %s." % (tag))

    conf = read_tag_configuration(tag)

    return flask.render_template("admin.html", tag = tag, conf = conf, \
        key = key, registered_iso = registered_iso, ttl_iso = ttl_iso, \
        title = "Administration for %s" % (tag))
     
#def nonblocking(pipe, size):
#    f = fcntl.fcntl(pipe, fcntl.F_GETFL)
# 
#    if not pipe.closed:
#        fcntl.fcntl(pipe, fcntl.F_SETFL, f | os.O_NONBLOCK)
# 
#    if not select.select([pipe], [], [])[0]:
#        yield ""
# 
#    while True:
#        data = pipe.read(size)
#
#        ## Stopper på StopIteration, så på break
#        if len(data) == 0:
#            break

@app.route("/archive/<tag>/")
@app.route("/archive/<tag>")
def archive(tag):
    def stream_archive(files_to_archive):
        command = "/usr/bin/zip -j - %s" % (" ".join(files_to_archive))
        p = subprocess.Popen(command, stdout=subprocess.PIPE, shell = True)
        f = fcntl.fcntl(p.stdout, fcntl.F_GETFL)
 
        while True:
            if not p.stdout.closed:
                fcntl.fcntl(p.stdout, fcntl.F_SETFL, f | os.O_NONBLOCK)
         
            if not select.select([p.stdout], [], [])[0]:
                yield ""

            data = p.stdout.read(4096)
            yield data
            if len(data) == 0:
                break

    if not verify(tag):
        time.sleep(failure_sleep)
        flask.abort(400)

    tag_path = get_path(tag)
    if not os.path.exists(tag_path):
        time.sleep(failure_sleep)
        flask.abort(404)

    files = get_files_in_tag(tag)
    files_to_archive = []
    for f in files:
        filepath = f['filepath']
        files_to_archive.append(filepath)
        log("INFO","Zip tag %s, file path %s" % (tag,filepath))

    h = werkzeug.Headers()
    #h.add('Content-Length', '314572800')
    h.add('Content-Disposition', 'attachment; filename=%s.zip' % (tag))
    return flask.Response(stream_archive(files_to_archive), mimetype='application/zip', headers = h, direct_passthrough = True)

@app.route("/upload/<tag>/")
@app.route("/upload/<tag>")
def upload_to_tag(tag):
    if not verify(tag):
        flask.abort(400)

    # Generate the administration only if the tag does not exist.
    key = False
    conf = read_tag_configuration(tag)

    if conf:
        # The tag is read only
        if conf['permission'] != 'rw':
            flask.abort(401)

    else:
        key = generate_key()
        create_default_tag_configuration(tag,key)

    return flask.render_template("upload.html", tag = tag, key = key, title = "Upload to tag %s" % (tag))

@app.route("/upload/")
@app.route("/upload")
def upload():
    tag = generate_tag()
    return flask.redirect('/upload/%s' % (tag))

@app.route("/download/", methods = ['POST', 'GET'])
@app.route("/download", methods = ['POST', 'GET'])
def download():
    if flask.request.method == 'POST':
        try:
            tag = flask.request.form['tag']
            if not verify(tag):
                tag = False

        except:
            tag = False

        if tag:
            return flask.redirect('/%s' % (tag))
        else:
            flask.abort(400)
    else:
        tags = get_public_tags()
        return flask.render_template("download.html" , tags = tags, \
            title = "Download")

@app.route("/uploader/", methods = ['POST'])
@app.route("/uploader", methods = ['POST'])
def uploader():
    status = False

    # Store values in a hash that is stored in db later
    i = {}
    i['client']   = get_client()
    i['filename'] = get_header('x-file-name')
    i['tag']      = get_header('x-tag')
    checksum      = get_header('content-md5')

    if not verify(i['tag'],i['filename']):
        flask.abort(400)

    # The input values are to be trusted at this point
    conf = read_tag_configuration(i['tag'])
    if conf:
        # The tag is read only
        if conf['permission'] != 'rw':
            flask.abort(401)

    # New flask.request from client
    log_prefix = '%s -> %s/%s' % (i['client'],i['tag'],i['filename'])
    log("INFO","%s: Upload request received" % (log_prefix))

    if not os.path.exists(temp_directory):
        os.makedirs(temp_directory)
        if not os.path.exists(temp_directory):
            log("ERROR","%s: Unable to create directory %s" % (\
                log_prefix,temp_directory))
            flask.abort(501)

    # The temporary destination (while the upload is still in progress)
    try:
        temp = tempfile.NamedTemporaryFile(dir = temp_directory)

    except:
        log("DEBUG","%s: Unable to create temp file %s" % \
            (log_prefix,temp.name))
        flask.abort(501)

    log("DEBUG","%s: Using %s as tempfile" % (log_prefix,temp.name))

    # The final destination
    target_dir = get_path(i['tag'])

    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        if not os.path.exists(target_dir):
            log("ERROR","%s: Unable to create directory %s" % (\
                log_prefix,target_dir))
            flask.abort(501)

    i['filepath'] = get_path(i['tag'],i['filename'])

    log("DEBUG","%s: Will save the content to %s" % ( \
        log_prefix,i['filepath']))
    
    # Stream the content directly to the temporary file on disk
    while 1:
        buf = sys.stdin.read(1)
        if buf:
            temp.write(buf)
    
        else:
            log("DEBUG","%s: Upload to tempfile complete" % (log_prefix))
            temp.seek(0)
            break

    # Verify the md5 checksum here.
    i['md5sum'] = md5_for_file(temp.name)
    log("DEBUG","%s: MD5-sum on uploaded file: %s" % (log_prefix, i['md5sum']))

    if checksum == i['md5sum']:
        log("DEBUG","%s: Checksum OK!" % (log_prefix))

    else:
        log("DEBUG","%s: Checksum mismatch! (%s != %s)" % ( \
            log_prefix, checksum, i['md5sum']))
        # TODO: Should abort here

    # Detect file type
    try:
        mimetype = get_mimetype(temp.name)

    except:
        pass

    else:
        i['mimetype'] = mimetype

    captured = False
    if mimetype:
         m = re.match('^image',mimetype)
         if m:
             captured_dt = get_time_of_capture(temp.name)

             if captured_dt:
                 try:
                     captured = int(captured_dt.strftime("%Y%m%d%H%M%S"))

                 except:
                     captured = captured_dt

    if captured:
        i['captured'] = captured

    try:
        stat = os.stat(temp.name)

    except:
        log("ERROR","%s: Unable to read size of temp file" % ( \
            log_prefix,temp.name))

    else:
        i['size'] = int(stat.st_size)

    # Uploading to temporary file is complete. Will now copy the contents 
    # to the final target destination.
    try:
        shutil.copyfile(temp.name,i['filepath'])

    except:
        log("ERROR","%s: Unable to copy tempfile (%s) to target " \
            "(%s)" % (log_prefix,temp.name,i['filepath']))

    else:
        log("DEBUG","%s: Content copied from tempfile (%s) to " \
            "final destination (%s)" % (log_prefix,temp.name, \
            i['filepath']))

        if not add_file_to_database(i):
            log("ERROR","%s: Unable to add file to database." % (log_prefix))

        else:
            # Log the activity
            dblog(i['client'],i['tag'],i['filename'],'upload')
            status = True

    # Clean up the temporary file
    temp.close()

    response = flask.make_response(flask.render_template('uploader.html'))

    if status:
        response.headers['status'] = '200'

    else:
        response.headers['status'] = '501'

    response.headers['content-type'] = 'text/plain'

    return response

@app.route("/maintenance/")
@app.route("/maintenance")
def maintenance():
    tags = get_tags()
    for tag in tags:
        if get_tag_lifetime(tag):
            #log("DEBUG","%s: TTL not reached" % (tag))
            generate_thumbnails(tag)

        else:
            log("INFO","%s: TTL reached. Should be deleted." % (tag))

            # Remove from tags and files
            # Remove from filesystem
            if remove_tag(tag):
                log("INFO","%s: Removed." % (tag))
            else:
                log("ERROR","%s: Unable to remove." % (tag))

            
    return flask.render_template("maintenance.html", title = "Maintenance")

@app.route("/robots.txt")
def robots():
    response = flask.make_response(flask.render_template('robots.txt'))
    response.headers['content-type'] = 'text/plain'
    return response

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0')
