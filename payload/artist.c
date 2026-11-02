/* Album artists. Firmware 2.3 ignores the iTunesDB's album-artist mhod (type
 * 22): the track loader's mhod switch (0xc4e64) only knows types 1-12. Every
 * list that groups by artist (Artists, an artist's albums, Genres) reads the
 * track record's artist (+0x28), so a track with an album artist gets that as
 * its artist instead: compilations and "feat." songs stay under one name.
 * Now Playing shows it too (docs/re-notes.md, "Album artists").
 *
 * mhod_hook (hooks.S) passes each mhod's type through album_artist_mhod()
 * before the switch, which then reads the string as the type returned. */

#include <stdint.h>

#define MHOD_SKIP          0       /* the switch's default: skip the mhod */
#define MHOD_ARTIST        4
#define MHOD_ALBUM_ARTIST  22

static uint32_t current;           /* the record being loaded */
static int from_album_artist;      /* its artist came from an album artist */

uint32_t album_artist_mhod(uint32_t type, uint32_t record)
{
    if (record != current) {
        current = record;
        from_album_artist = 0;
    }
    if (type == MHOD_ALBUM_ARTIST) {
        /* Read as the artist. An artist mhod read before this one is
         * replaced: the artist case stores whatever string it reads last. */
        from_album_artist = 1;
        return MHOD_ARTIST;
    }
    if (type == MHOD_ARTIST && from_album_artist)
        return MHOD_SKIP;
    return type;
}
