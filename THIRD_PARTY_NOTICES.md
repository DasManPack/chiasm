# Third-Party Notices

Chiasm-specific work and inherited Melodex code are MIT licensed unless a subdirectory states otherwise. The notices below document upstream-derived foundations, design inspiration, and external services or content used at runtime. External music, artwork and metadata are not relicensed under either project's MIT licence.

## Parachord

Chiasm is a separate project derived from Melodex. The inherited multi-source resolver design was inspired in part by Parachord and by the earlier Tomahawk approach to source-neutral music playback.

Parachord: https://github.com/Parachord/parachord

Parachord is licensed under the MIT License.

Copyright (c) 2025 Jason Herskowitz

The full Parachord MIT license is reproduced in `docs/licenses/PARACHORD-LICENSE.txt`.

The resolver code added to Melodex was independently implemented rather than copied from Parachord source files. This notice documents design inspiration and retained upstream attribution.

## MusicBrainz / MetaBrainz Foundation

Melodex can retrieve recording, artist, release, relationship, tag/genre and credit metadata from MusicBrainz.

MusicBrainz licensing is split by data category:

- core database data: CC0 1.0 / public-domain dedication;
- supplementary data: CC BY-NC-SA 3.0.

See: https://musicbrainz.org/doc/About/Data_License

MusicBrainz/MetaBrainz names and marks remain the property of their respective owners. Melodex is not affiliated with or endorsed by MetaBrainz.

## Cover Art Archive

Melodex can retrieve release artwork from the Cover Art Archive, a collaboration between MusicBrainz and the Internet Archive.

See: https://musicbrainz.org/doc/Cover_Art_Archive

Cover images may remain copyrighted by artists, labels, designers or other rightsholders. The archive does not provide a single blanket copyright licence for all images, and Melodex does not relicense them.

## Wikidata

Melodex may use Wikidata to follow structured links between a MusicBrainz artist and a Wikimedia Commons image.

Wikidata structured data is released under Creative Commons CC0.

See: https://www.wikidata.org/wiki/Wikidata:Licensing

## Wikimedia Commons

Melodex may display artist photographs hosted on Wikimedia Commons when linked through Wikidata.

Each Commons file can have different copyright/licence and attribution requirements. Reusers should follow the author, licence, attribution and share-alike requirements shown on that file's description page. Melodex does not relicense Commons media.

See: https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia

**Implementation note:** README-level attribution does not replace per-file credit when an image licence requires it. Melodex should expose the specific Commons file's author/licence/link in the UI before artist-photo support is treated as fully attribution-complete.

## Jamendo

Jamendo is included as an optional reference provider. Users supply their own Jamendo developer Client ID.

Jamendo API terms require applications to credit the creator, credit Jamendo as provider, and provide a direct backlink from each item to its relevant Jamendo content page. Melodex's Jamendo provider preserves creator attribution, the track licence URL and the Jamendo source-page link.

See:
- https://devportal.jamendo.com/api_terms_of_use
- https://developer.jamendo.com/v3.0/tracks

Melodex is not affiliated with or endorsed by Jamendo.

## Python and application dependencies

Melodex uses third-party Python/application dependencies such as PySide6, requests, NumPy, mutagen and the optional MCP SDK. Those packages retain their own licences and copyright notices. Refer to each dependency's distribution metadata/upstream repository for its applicable licence.
