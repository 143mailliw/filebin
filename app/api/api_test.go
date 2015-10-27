package api

import (
	"testing"
	"math/rand"
	"encoding/hex"
	"io/ioutil"
	"os"
)

func TestTriggers(t *testing.T) {
	var err error

	err = triggerNewTagHandler("/bin/echo", "tag")
	if err != nil {
		t.Fatal(err)
	}

	err = triggerUploadedFileHandler("/bin/echo", "tag", "filename")
	if err != nil {
		t.Fatal(err)
	}

	err = triggerExpiredTagHandler("/bin/echo", "tag")
	if err != nil {
		t.Fatal(err)
	}
}

func TestSha256Sum(t *testing.T) {
	file, err := ioutil.TempFile(os.TempDir(), "prefix")
	defer os.Remove(file.Name())
	file.WriteString("some content")
	file.Sync()
	checksum, err := sha256sum(file.Name())
	if err != nil {
		t.Fatal(err)
	}

	sum := hex.EncodeToString(checksum)
	if sum != "290f493c44f5d63d06b374d0a5abd292fae38b92cab2fae5efefe1b0e9347f56" {
		t.Fatal("Invalid checksum", sum)
	}
}

func TestIsDir(t *testing.T) {
	if isDir("/etc") == false {
		t.Fatal("Unable to detect /etc as a directory")
	}

	if isDir("/unknowndirectory") != false {
		t.Fatal("Non existing path should not be a directory")
	}

	file, err := ioutil.TempFile(os.TempDir(), "prefix")
	if err != nil {
		t.Fatal(err)
	}
	defer os.Remove(file.Name())
	if isDir(file.Name()) != false {
		t.Fatal("File", file.Name(), "is not a directory")
	}
}

func TestRandomString(t *testing.T) {
	rand.Seed(1)
	str := randomString(16)
	if str != "fpllngzieyoh43e0" {
		t.Fatal("Random string from known seed is not", str)
	}
}

func TestSanitizeFilename(t *testing.T) {
	var str string
	str = sanitizeFilename("foo")
	if str != "foo" {
		t.Fatal("Sanitizing failed:", str)
	}

	str = sanitizeFilename(" foo!\"#$%&()= ")
	if str != "foo________=" {
		t.Fatal("Sanitizing failed:", str)
	}

	str = sanitizeFilename("/foo/bar/baz")
	if str != "baz" {
		t.Fatal("Sanitizing failed:", str)
	}
}
