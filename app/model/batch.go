package model

import (
	"github.com/espebra/filebin/app/backend/fs"
	"log"
	"math/rand"
	"time"
)

// Dispatcher function to spawn a number of workers
func StartDispatcher(nworkers int, CacheInvalidation bool, WorkQueue chan Job, log *log.Logger, backend *fs.Backend) {
	for i := 0; i < nworkers; i++ {
		go StartWorker(CacheInvalidation, WorkQueue, log, backend)
	}
}

func StartWorker(CacheInvalidation bool, WorkQueue chan Job, log *log.Logger, backend *fs.Backend) {
	for {
		select {
		case j := <-WorkQueue:
			startTime := time.Now().UTC()

			if err := backend.GenerateThumbnail(j.Bin, j.Filename, 115, 115, true); err != nil {
				log.Println("Batch job error: " + j.Bin + "/" + j.Filename + " (" + err.Error() + ")")
				break
			}

			if err := backend.GenerateThumbnail(j.Bin, j.Filename, 1140, 0, false); err != nil {
				log.Println("Batch job error: " + j.Bin + "/" + j.Filename + " (" + err.Error() + ")")
				break
			}

			//if CacheInvalidation {
			//	if err := f.Purge(); err != nil {
			//		log.Print(err)
			//	}
			//}

			finishTime := time.Now().UTC()
			elapsedTime := finishTime.Sub(startTime)
			log.Println("Batch job completed: " + j.Bin + "/" + j.Filename + " (" + elapsedTime.String() + ")")
		}
	}
}

func randomString(n int) string {
	var letters = []rune("abcdefghijklmnopqrstuvwxyz0123456789")
	b := make([]rune, n)
	for i := range b {
		b[i] = letters[rand.Intn(len(letters))]
	}
	return string(b)
}
