package api

import (
	"os/exec"
	"time"
	"strconv"
	"net/http"
	"path/filepath"
	"github.com/gorilla/mux"
	"github.com/espebra/filebin/app/config"
	"github.com/espebra/filebin/app/model"
	"github.com/espebra/filebin/app/output"
)

func triggerNewTagHandler(c string, tag string) error {
	cmd := exec.Command(c, tag)
	err := cmdHandler(cmd)
	return err
}

func triggerUploadedFileHandler(c string, tag string, filename string) error {
	cmd := exec.Command(c, tag, filename)
	err := cmdHandler(cmd)
	return err
}

func triggerExpiredTagHandler(c string, tag string) error {
	cmd := exec.Command(c, tag)
	err := cmdHandler(cmd)
	return err
}

func cmdHandler(cmd *exec.Cmd) error {
	err := cmd.Start()
	return err
}

func Upload(w http.ResponseWriter, r *http.Request, cfg config.Configuration, ctx model.Context) {
	var err error
	f := model.ExtendedFile { }

	// Extract the tag from the request
	if (r.Header.Get("tag") == "") {
		err = f.GenerateTagID()
		ctx.Log.Println("Tag generated: " + f.TagID)
	} else {
		tag := r.Header.Get("tag")
		err = f.SetTagID(tag)
		ctx.Log.Println("Tag specified: " + tag)
	}
	if err != nil {
		ctx.Log.Println(err)
		http.Error(w, err.Error(), http.StatusBadRequest);
		return
	}
	ctx.Log.Println("Tag: " + f.TagID)
	f.SetTagDir(cfg.Filedir)
	ctx.Log.Println("Tag directory: " + f.TagDir)

	// Write the request body to a temporary file
	err = f.WriteTempfile(r.Body, cfg.Tempdir)
	if err != nil {
		ctx.Log.Println("Unable to write tempfile: ", err)

		// Clean up by removing the tempfile
		f.ClearTemp()

		http.Error(w, "Internal Server Error", http.StatusInternalServerError);
		return
	}
	ctx.Log.Println("Tempfile: " + f.Tempfile)
	ctx.Log.Println("Tempfile size: " + strconv.FormatInt(f.Bytes, 10) + " bytes")

	// Do not accept files that are 0 bytes
	if f.Bytes == 0 {
		ctx.Log.Println("Empty files are not allowed. Aborting.")

		// Clean up by removing the tempfile
		f.ClearTemp()

		http.Error(w, "No content. The file size must be more than " +
			"0 bytes.", http.StatusBadRequest);
		return
	}

	// Calculate and verify the checksum
	checksum := r.Header.Get("content-sha256")
	if checksum != "" {
		ctx.Log.Println("Checksum specified: " + checksum)
	}
	err = f.VerifySHA256(checksum)
	ctx.Log.Println("Checksum calculated: " + f.Checksum)
	if err != nil {
		ctx.Log.Println("The specified checksum did not match")
		http.Error(w, "Checksum did not match", http.StatusConflict);
		return
	}

	// Trigger new tag
	if !f.TagDirExists() {
		if cfg.TriggerNewTag != "" {
			ctx.Log.Println("Executing trigger: New tag")
			triggerNewTagHandler(cfg.TriggerNewTag, f.TagID)
		}
	}

	// Create the tag directory if it does not exist
	err = f.EnsureTagDirectoryExists()
	if err != nil {
		ctx.Log.Println("Unable to create tag directory: ", f.TagDir)
		http.Error(w, "Internal Server Error", http.StatusInternalServerError);
		return
	}

	f.CalculateExpiration(cfg.Expiration)
	expired, err := f.IsExpired(cfg.Expiration)
	if err != nil {
		ctx.Log.Println(err)
		http.Error(w,"Internal server error", 500)
		return
	}
	if expired {
		ctx.Log.Println("The tag has expired. Aborting.")
		http.Error(w,"This tag has expired.", 410)
		return
	}

	// Extract the filename from the request
	fname := r.Header.Get("filename")
	if (fname == "") {
		ctx.Log.Println("Filename generated: " + f.Checksum)
		f.SetFilename(f.Checksum)
	} else {
		ctx.Log.Println("Filename specified: " + fname)
		err = f.SetFilename(fname)
		if err != nil {
			ctx.Log.Println(err)
			http.Error(w, "Invalid filename specified. It contains illegal characters or is too short.",
				http.StatusBadRequest);
			return
		}
	}

	if fname != f.Filename {
		ctx.Log.Println("Filename sanitized: " + f.Filename)
	}

	// Promote file from tempdir to the published tagdir
	f.Publish()

	// Clean up by removing the tempfile
	f.ClearTemp()

	err = f.DetectMIME()
	if err != nil {
		ctx.Log.Println("Unable to detect MIME: ", err)
	} else {
		ctx.Log.Println("MIME detected: " + f.MIME)
	}

	err = f.Info()
	if err != nil {
		ctx.Log.Println(err)
		http.Error(w,"Internal Server Error", 500)
		return
	}

	f.GenerateLinks(cfg.Baseurl)
	f.RemoteAddr = r.RemoteAddr
	f.UserAgent = r.Header.Get("User-Agent")
	f.CreatedAt = time.Now().UTC()
	//f.ExpiresAt = time.Now().UTC().Add(24 * 7 * 4 * time.Hour)

	if cfg.TriggerUploadedFile != "" {
		ctx.Log.Println("Executing trigger: Uploaded file")
		triggerUploadedFileHandler(cfg.TriggerUploadedFile, f.TagID, f.Filename)
	}

	headers := make(map[string]string)
	headers["Content-Type"] = "application/json"

	var status = 201
	output.JSONresponse(w, status, headers, f, ctx)
}

func FetchFile(w http.ResponseWriter, r *http.Request, cfg config.Configuration, ctx model.Context) {
	var err error
	params := mux.Vars(r)
	f := model.File {}
	f.SetFilename(params["filename"])
	if err != nil {
		ctx.Log.Println(err)
		http.Error(w,"Invalid filename specified. It contains illegal characters or is too short.", 400)
		return
	}
	err = f.SetTagID(params["tag"])
	if err != nil {
		ctx.Log.Println(err)
		http.Error(w,"Invalid tag specified. It contains illegal characters or is too short.", 400)
		return
	}
	f.SetTagDir(cfg.Filedir)

	f.CalculateExpiration(cfg.Expiration)
	expired, err := f.IsExpired(cfg.Expiration)
	if err != nil {
		ctx.Log.Println(err)
		http.Error(w,"Internal server error", 500)
		return
	}
	if expired {
		ctx.Log.Println("Expired: " + f.ExpirationReadable)
		http.Error(w,"This tag has expired.", 410)
		return
	}
	
	path := filepath.Join(f.TagDir, f.Filename)
	
	w.Header().Set("Cache-Control", "max-age=1")
	http.ServeFile(w, r, path)
}

func DeleteFile(w http.ResponseWriter, r *http.Request, cfg config.Configuration, ctx model.Context) {
	var err error
	params := mux.Vars(r)
	f := model.File {}
	f.SetFilename(params["filename"])
	if err != nil {
		ctx.Log.Println(err)
		http.Error(w,"Invalid filename specified. It contains illegal characters or is too short.", 400)
		return
	}
	err = f.SetTagID(params["tag"])
	if err != nil {
		ctx.Log.Println(err)
		http.Error(w,"Invalid tag specified. It contains illegal characters or is too short.", 400)
		return
	}
	f.SetTagDir(cfg.Filedir)

	if f.Exists() == false {
		ctx.Log.Println("The file does not exist.")
		http.Error(w,"File Not Found", 404)
		return
	}

	f.CalculateExpiration(cfg.Expiration)
	expired, err := f.IsExpired(cfg.Expiration)
	if err != nil {
		ctx.Log.Println(err)
		http.Error(w,"Internal server error", 500)
		return
	}
	if expired {
		ctx.Log.Println("Expired: " + f.ExpirationReadable)
		http.Error(w,"This tag has expired.", 410)
		return
	}

	f.GenerateLinks(cfg.Baseurl)
	err = f.DetectMIME()
	if err != nil {
		ctx.Log.Println("Unable to detect MIME: ", err)
	}

	err = f.Info()
	if err != nil {
		ctx.Log.Println(err)
		http.Error(w,"Internal Server Error", 500)
		return
	}

	err = f.Remove()
 	if err != nil {
		ctx.Log.Println("Unable to remove file: ", err)
		http.Error(w,"Internal Server Error", 500)
		return
	}

	headers := make(map[string]string)
	headers["Content-Type"] = "application/json"

	var status = 200
	output.JSONresponse(w, status, headers, f, ctx)
	return
}

func FetchTag(w http.ResponseWriter, r *http.Request, cfg config.Configuration, ctx model.Context) {
	var err error
	params := mux.Vars(r)
	t := model.ExtendedTag {}
	err = t.SetTagID(params["tag"])
	if err != nil {
		ctx.Log.Println(err)
		http.Error(w, "Invalid tag", 400)
		return
	}

	t.SetTagDir(cfg.Filedir)
	t.CalculateExpiration(cfg.Expiration)
	if t.TagDirExists() {
		expired, err := t.IsExpired(cfg.Expiration)
		if err != nil {
			ctx.Log.Println(err)
			http.Error(w,"Internal server error", 500)
			return
		}
		if expired {
			ctx.Log.Println("Expired: " + t.ExpirationReadable)
			http.Error(w,"This tag has expired.", 410)
			return
		}

		err = t.Info()
		if err != nil {
			ctx.Log.Println(err)
			http.Error(w, "Internal Server Error", 500)
			return
		}

		err = t.List(cfg.Baseurl)
		if err != nil {
			ctx.Log.Println(err)
			http.Error(w,"Some error.", 404)
			return
		}
	}

	//t.GenerateLinks(cfg.Baseurl)

	headers := make(map[string]string)
	headers["Cache-Control"] = "max-age=1"

	var status = 200

	if (r.Header.Get("Content-Type") == "application/json") {
		headers["Content-Type"] = "application/json"
		output.JSONresponse(w, status, headers, t, ctx)
	} else {
		output.HTMLresponse(w, "viewtag", status, headers, t, ctx)
	}
}

func ViewIndex(w http.ResponseWriter, r *http.Request, cfg config.Configuration, ctx model.Context) {
	t := model.Tag {}
	err := t.GenerateTagID()
	if err != nil {
		ctx.Log.Println(err)
		http.Error(w, "Internal Server Error", 500)
		return
	}
	ctx.Log.Println("Tag generated: " + t.TagID)

	headers := make(map[string]string)
	headers["Cache-Control"] = "max-age=0"
	headers["Location"] = ctx.Baseurl + "/" + t.TagID
	var status = 302
	output.JSONresponse(w, status, headers, t, ctx)
}

func ViewAPI(w http.ResponseWriter, r *http.Request, cfg config.Configuration, ctx model.Context) {
	t := model.Tag {}
	headers := make(map[string]string)
	headers["Cache-Control"] = "max-age=1"
	var status = 200
	output.HTMLresponse(w, "api", status, headers, t, ctx)
}

func ViewDoc(w http.ResponseWriter, r *http.Request, cfg config.Configuration, ctx model.Context) {
	t := model.Tag {}
	headers := make(map[string]string)
	headers["Cache-Control"] = "max-age=1"
	var status = 200
	output.HTMLresponse(w, "doc", status, headers, t, ctx)
}
