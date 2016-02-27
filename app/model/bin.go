package model

import (
	"errors"
	"io/ioutil"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"time"

	"github.com/dustin/go-humanize"
)

type Bin struct {
	Bin                string    `json:"bin"`
	BinDir             string    `json:"-"`
	Bytes              int64     `json:"bytes"`
	ExpirationAt       time.Time `json:"expiration"`
	Expired            bool      `json:"-"`
	LastUpdateAt       time.Time `json:"lastupdate"`
	Files              []File    `json:"files"`

	Album bool `json:"-"`
}

//func (t *Bin) GenerateBin() error {
//	var bin = randomString(16)
//	err := t.SetBin(bin)
//	return err
//}

func (t *Bin) SetBin(s string) error {
	validBin := regexp.MustCompile("^[a-zA-Z0-9-_]{8,}$")
	if validBin.MatchString(s) == false {
		return errors.New("Invalid bin specified. It contains " +
			"illegal characters or is too short")
	}
	t.Bin = s
	return nil
}

func (t *Bin) SetBinDir(filedir string) {
	t.BinDir = filepath.Join(filedir, t.Bin)
}

func (t *Bin) BinDirExists() bool {
	if isDir(t.BinDir) {
		return true
	} else {
		return false
	}
}

func (t *Bin) StatInfo() error {
	if isDir(t.BinDir) == false {
		return errors.New("Bin does not exist.")
	}

	i, err := os.Lstat(t.BinDir)
	if err != nil {
		return err
	}
	t.LastUpdateAt = i.ModTime().UTC()
	return nil
}

func (t *Bin) IsExpired(expiration int64) (bool, error) {
	now := time.Now().UTC()

	// Calculate if the bin is expired or not
	if now.Before(t.ExpirationAt) {
		// Bin still valid
		return false, nil
	} else {
		// Bin expired
		t.Expired = true
		return true, nil
	}
}

func (t *Bin) CalculateExpiration(expiration int64) error {
	i, err := os.Lstat(t.BinDir)
	if err == nil {
		t.ExpirationAt = i.ModTime().UTC().Add(time.Duration(expiration) * time.Second)
	} else {
		t.ExpirationAt = time.Now().UTC().Add(time.Duration(expiration) * time.Second)
	}
	return nil
}

func (t *Bin) Remove() error {
	if t.BinDir == "" {
		return errors.New("Bin dir is not set")
	}
	err := os.RemoveAll(t.BinDir)
	return err
}

func (t *Bin) List(baseurl string) error {
	files, err := ioutil.ReadDir(t.BinDir)
	for _, file := range files {
		// Do not care about sub directories (such as .cache)
		if file.IsDir() == true {
			continue
		}

		var f = File{}
		f.SetFilename(file.Name())
		f.SetBin(t.Bin)
		f.BinDir = t.BinDir

		if err := f.StatInfo(); err != nil {
			return err
		}

		if err := f.DetectMIME(); err != nil {
			return err
		}

		if f.MediaType() == "image" {
			// Set this list of files as an album
			t.Album = true

			if err := f.ParseExif(); err != nil {
				// XXX: Log this
			}
		}

		f.GenerateLinks(baseurl)

		// Calculate the total amount of bytes in the bin
		t.Bytes = t.Bytes + f.Bytes

		t.Files = append(t.Files, f)
	}
	sort.Sort(FilesByDateTime(t.Files))
	return err
}

func (t Bin) BytesReadable() string {
	return humanize.Bytes(uint64(t.Bytes))
}

func (t Bin) LastUpdateReadable() string {
	return humanize.Time(t.LastUpdateAt)
}

func (t Bin) ExpirationReadable() string {
	return humanize.Time(t.ExpirationAt)
}
