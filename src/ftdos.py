#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
# vim: set ts=4 ai :
#
# $Id: sedoric.py $
# $Author: assinie <github@assinie.info> $
# $Date: 2018-02-27 $
# $Revision: 0.4 $
#
# ------------------------------------------------------------------------------

from __future__ import print_function

from pprint import pprint

import os

import sys
import struct

import argparse
import fnmatch

# ------------------------------------------------------------------------------
__program_name__ = 'ftdos'
__description__ = "Gestion des images FTDOS"
__plugin_type__ = "OS"
__version__ = 0.2


# ------------------------------------------------------------------------------
def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


FILTER = ''.join([(len(repr(chr(x))) == 3) and chr(x) or '.' for x in range(256)])


def dump(src, offset=0, length=16):
    N = 0
    result = ''
    while src:
        s, src = src[:length], src[length:]
        hexa = ' '.join(["%02X" % ord(x) for x in s])
        s = s.translate(FILTER)
        result += "%04X   %-*s   %s\n" % (N + offset, length * 3, hexa, s)
        N += length
    return result


# ------------------------------------------------------------------------------
class ftdos():
    def __init__(self, source='DEFAULT', verbose=0):
        self.dirents = {}
        self.source = source
        self.offset = 0
        self.sides = 2
        self.tracks = 41
        self.sectors = 17
        self.sectorsize = 256
        self.geometry = 1
        self.signature = 'MFM_DISK'
        self.diskname = ''
        self.dostype = 'FTDOS'
        self.dos = ''
        self.disktype = ''

        self.crc = 0
        self.trackbuf = []
        self.ptr_track = 0
        self.diskimg = []

        self.verbose = verbose

    def validate(self, diskimg):
        ret = None

        try:
            diskimg = os.path.abspath(diskimg)

            with open(diskimg, 'rb') as f:
                self.signature = f.read(8)

                if self.signature != 'MFM_DISK':
                    print("Erreur signature '%s' incorrecte pour %s" % (self.signature, diskimg))
                else:
                    self.source = diskimg

                    # print('Lecture 20/1')
                    track = self.read_track(20, 0)
                    offset = track['sectors'][1]['data_ptr'] + 1
                    dos = track['raw'][offset:offset + 256][246:248]

                    if dos == chr(0x80) + chr(0x80) or dos == chr(0x80) + chr(0x4d):
                        # print('Lecture 20/2')
                        offset = track['sectors'][2]['data_ptr'] + 1
                        dos = track['raw'][offset:offset + 256][0:2]

                        if dos == chr(0x00) + chr(0x00):

                            self.dos = 'FT-Dos'

                            self.sectors = len(track['sectors'])
                            self.offset = 0x100
                            self.sectorsize = 256

                            self.sides = struct.unpack("<L", f.read(4))[0]
                            self.tracks = struct.unpack("<L", f.read(4))[0]
                            self.geometry = struct.unpack("<L", f.read(4))[0]

                            ret = {'source': diskimg,
                                    'dos': self.dos,
                                    'sides': self.sides,
                                    'tracks': self.tracks,
                                    'sectors': self.sectors,
                                    'sectorsize': self.sectorsize,
                                    'geometry': self.geometry,
                                    'offset': self.offset
                                }

                            # self.read_diskname()
                            # self.read_dir()
                            # self.loaddisk()
                        else:
                            print('Echec')
                            print(dump(track['raw'][offset:offset + 256][0:256]))
                            print(dump(dos))
                    else:
                        print('Echec')
                        print(dump(track['raw'][offset:offset + 256][0:256]))
                        print(dump(dos))

        except IOError as e:
            eprint(e)
            self.source = None
            ret = None

        return ret

    def read_track(self, track, side):
        # print('***read_track(%s): Track=%d/%d, Side=%d' % (__name__, track, self.tracks, side))
        sector = {}
        read_track = {}

        if self.signature != 'MFM_DISK':
            return sector

        with open(self.source, 'rb') as f:
            ptr = self.offset + (side * self.tracks + track) * 6400
            f.seek(ptr)
            # print f.tell()
            raw = f.read(6400)
            read_track['raw'] = raw
            sectorcount = 0
            ptr = 0
            eot = 6400

            while ptr < eot:
                while ptr < eot and ord(raw[ptr]) != 0xfe:
                    ptr += 1

                if ptr >= eot:
                    break

                S = ord(raw[ptr + 3])
                P = ord(raw[ptr + 1])
                # print 'found sector: P:%d S:%d (%d)' % (P, S, sectorcount)

                sector[S] = {}
                sector[S]['id_ptr'] = ptr
                sector[S]['data_ptr'] = -1

                sectorcount += 1
                # ID field
                n = ord(raw[ptr + 4])
                # print 'ID: ', n
                # skip ID field & crc
                ptr += 7

                while ptr < eot and ord(raw[ptr]) != 0xfb and ord(raw[ptr]) != 0xfe:
                    ptr += 1

                if ptr >= eot:
                    break

                sector[S]['data_ptr'] = ptr

                # Skip data field and ID
                ptr += (1 << (n + 7)) + 3
            # print sectorcount
        f.close()
        read_track['sectors'] = sector

        return read_track

    def read_diskname(self):
        P = 20
        S = 1
        track = self.read_track(P, 0)

        # Calcul de l'offset du secteur (+1 pour sauter l'ID)
        offset = track['sectors'][S]['data_ptr'] + 1
        cat = track['raw'][offset:offset + 256]

        self.diskname = cat[-8:]
        # print(dump(cat))

        return self.diskname

    def read_dir(self):
        self.dirents = self.FTDOS_cat()
        # self.dirents['BOOTSECT.BIN'] = {'side': 0, 'track': 0, 'sector': 1, 'lock': 'L', 'type': 'D', 'size': 1, 'content_type': 'asm'}
        return self.dirents

    def read_file(self, filename):
        if filename == 'FTDOS3-2.SYS' or filename == 'TDOS2-26.SYS':
            # 0 => ROM 1.1 ou disquette !MASTER
            # 4 => ROM 1.0
            file = self.FTDOS_getsys(4)
            size = len(file)
            start = 0xc000
            # self.FTDOS_desass(file)
            return {'file': file[0:size], 'start': start, 'size': size, 'end': start+size, 'type': 0x40, 'exec': 0xd4f8}

        elif filename == 'BOOTSECT.BIN':
            track = self.read_track(0, 0)

            offset = track['sectors'][1]['data_ptr'] + 1
            cat = track['raw'][offset:offset + 256]
            return {'file': cat, 'start': 0x400, 'size': 256}

        else:
            return self.FTDOS_read_file(filename)

    def _cat(self):
        if len(self.dirents) == 0:
            self.read_dir()

        for filename in sorted(self.dirents.keys()):
            print('S:%01d P:%02d S:%02d        %c %s %3d   %c (%s)' % (
                    self.dirents[filename]['side'],
                    self.dirents[filename]['track'],
                    self.dirents[filename]['sector'],
                    self.dirents[filename]['lock'],
                    filename,
                    self.dirents[filename]['size'],
                    self.dirents[filename]['type'],
                    self.dirents[filename]['content_type'])
                    )

    def display_bitmap(self):
        return self.FTDOS_display_bitmap()

    def FTDOS_cat(self):
        dirents = {}

        # Lecture premier secteur du catalogue S:0 P:20 S:2

        P = 20
        S = 2
        while P != 0xff and S != 0x00:
            track = self.read_track(P, 0)

            offset = track['sectors'][S]['data_ptr'] + 1
            cat = track['raw'][offset:offset + 256]

            # print('DIR P:%d S:%d' % (P, S))
            # print(dump(cat))

            # Doit etre egale a la piste et au secteur lu si on n'est pas
            # sur le premier secteur du catalogue (P:20 S:2)
            P = ord(cat[0])
            S = ord(cat[1])
            # print 'P:%d S:%d' %(P, S)

            # Chainage vers le catalogue suivant: FF 00 si dernier secteur
            # ou 00 00 si premier secteur et catalogue vide
            P = ord(cat[2])
            S = ord(cat[3])
            # print 'P:%d S:%d' %(P, S)

            for i in range(0, 14):
                entry_offset = 4 + i * 18
                entry = self.FTDOS_DirEntry(cat[entry_offset:entry_offset + 18])
                if len(entry) > 0:
                    dirents[entry.keys()[0]] = entry.values()[0]

        return dirents

    def FTDOS_DirEntry(self, entry):
        track = ord(entry[0])
        sector = ord(entry[1])
        lock = entry[2]

        name = entry[3:15]
        stripped_name = name[0:8].rstrip()
        stripped_ext = name[9:12].rstrip()
        if stripped_ext > '':
            stripped_name = stripped_name + '.' + stripped_ext

        type = entry[15]
        size = struct.unpack('<H', entry[16:18])[0]
        side = 0

        if track != 255:
            # print 'P:%02d S:%02d %c %s %c %d' % (track, sector, lock, name, type, len)
            # print '%c  %s  %c       %d SECTORS' % (lock, name, type, len)
            if name[-3:] == 'BAS':
                content_type = 'basic'
            elif name[-3:] in ['CMD', 'SYS', 'BIN']:
                # content_type = '6502'
                content_type = 'asm'
            elif name[-3:] == 'ARY':
                content_type = 'array'
            elif name[-3:] == 'SCR':
                if size == 6:
                    content_type = 'lscreen'
                else:
                    content_type = 'hscreen'
            elif name[-3:] == 'DAT':
                content_type = 'data'
            elif name[-3:] == 'TXT':
                content_type = 'text'
            else:
                content_type = '???'

            return {name: {'stripped_name': stripped_name, 'side': side, 'track': track, 'sector': sector, 'lock': lock, 'type': type, 'size': size, 'content_type': content_type}}

        return {}

    def FTDOS_read_file(self, filename):
        file = ''
        start = -1
        size = 0
        last_track_read = -1
        first_FCB = True

        if filename in self.dirents:
            P_FCB = self.dirents[filename]['track']
            S_FCB = self.dirents[filename]['sector']

            # Fichier de type 'S'
            #if self.verbose:
            #    print('*** ',filename)

            while P_FCB != 0xff and S_FCB != 0x00:
                if P_FCB != last_track_read:
                    track = self.read_track(P_FCB, 0)
                    last_track_read = P_FCB
                # else:
                #         print('***read_file: track already read (T: %d, S:%d)' % (P_FCB, S_FCB))

                offset = track['sectors'][S_FCB]['data_ptr'] + 1
                fcb = track['raw'][offset:offset + 256]
                # print  map (lambda s: hex(s), struct.unpack('256B',cat))

                # print('***read_file (%s): %s' % (__name__, filename))
                # print('***read_file: FCB (T: %d, S: %d)' % (P_FCB, S_FCB))
                #if self.verbose:
                #    print(dump(fcb))

                # Chainage vers le FCB suivant
                P_FCB = ord(fcb[0])
                S_FCB = ord(fcb[1])
                # print('***read_file (%s) Next FCB P:%d S:%d' % (__name__, P_FCB, S_FCB))

                if first_FCB is True:
                    first_FCB = False
                    start = struct.unpack('<H', fcb[2:4])[0]
                    size = struct.unpack('<H', fcb[4:6])[0]

                    # Correction bug FTDOS-3.2, la taille indiquee pour les tableaux
                    # et les ecrans
                    # fait 1 octet de moins que la realite!!!
                    if filename[-3:] == 'ARY':
                        size += size % 2
                    if filename[-3:] == 'SCR':
                        size += 1

                    # Calcule un type Sedoric
                    # Execution := 0x000
                    # Type      := Data
                    exec_addr = 0x00
                    type = 0x40

                    if filename[-3:] == 'BAS':
                        type = 0x80
                    elif filename[-3:] in ['CMD', 'SYS', 'BIN']:
                        exec_addr = start

                    if self.verbose:
                        print('Fichier              : ', filename)
                        print('Type                 :  %02X' % (type) )
                        print('Adresse de chargement: ', hex(start))

                        if exec_addr == 0x40:
                            print('Adresse Execution    : ', hex(exec_addr))

                        print('Taille               : ', size)
                        print('')

                n = 6
                P = 0
                S = 0
                while n <= 254 and P != 0xff and S != 0xff:
                    P = ord(fcb[n])
                    S = ord(fcb[n + 1])
                    n += 2

                    if P != 0xff and S != 0xff:
                        # print 'Lecture P:%d S:%d' % (P,S)
                        if P != last_track_read:
                            track = self.read_track(P, 0)
                            last_track_read = P
                        # else:
                        #     print('***read_file: track already read (T: %d, S:%d)' % (P, S))

                        offset = track['sectors'][S]['data_ptr'] + 1
                        file += track['raw'][offset:offset + 256]

        return {'file': file[0:size], 'start': start, 'size': size, 'end': start+size, 'exec': exec_addr, 'type': type }

    def FTDOS_getsys(self, start_track=0):
        # ROM v1.1  0 -> 2 + 11 secteurs de la 3
        # ROM v1.0  4 -> 6 + 11 secteurs de la 7

        FTDOS = ''

        # On lit 3 pistes
        for P in range(start_track, start_track + 3):
            # print('P =', P)
            track = self.read_track(P, 0)
            start_sector = 1
            end_sector = self.sectors
            if P == start_track:
                # Si c'est la premiere piste, on commence au secteur 3
                start_sector = 3

            for S in range(start_sector, end_sector + 1):
                offset = track['sectors'][S]['data_ptr'] + 1
                FTDOS += track['raw'][offset:offset + 256]

        # Lecture des 11 secteurs de la piste suivante
        P = start_track + 3
        track = self.read_track(P, 0)
        for S in range(1, 11 + 1):
            offset = track['sectors'][S]['data_ptr'] + 1
            FTDOS += track['raw'][offset:offset + 256]

        return FTDOS

    def FTDOS_display_bitmap(self):
        P = 20
        S = 1

        track = self.read_track(P, 0)
        offset = track['sectors'][S]['data_ptr'] + 1
        raw = track['raw'][offset:offset + 256]
        print(dump(raw))

        out = []
        for P in range(0, self.tracks):
            out.append('Track %02d: ' % P)

        for P in range(0, self.tracks * self.sides):
            bitmap = []
            bitmap.append(ord(raw[P * 3 + 2:P * 3 + 3]))
            bitmap.append(ord(raw[P * 3 + 1:P * 3 + 2]))
            bitmap.append(ord(raw[P * 3:P * 3 + 1]))

            if P >= self.tracks:
                    out[P % self.tracks] += ' : '

            out[P % self.tracks] += '%02X %02X %02X ' % (bitmap[0], bitmap[1], bitmap[2])

            if bitmap[0] >= 0x80:
                out[P % self.tracks] += '* * * * * * * * * * * * * * * * * '
            else:
                if bitmap[0] & 0x01 == 0x01:
                    out[P % self.tracks] += '. '
                else:
                    out[P % self.tracks] += '* '

                for i in range(1, 3):
                    for j in range(7, -1, -1):
                        if (bitmap[i] & 2**j == 2**j):
                            out[P % self.tracks] += '. '
                        else:
                            out[P % self.tracks] += '* '

        return out


# ------------------------------------------------------------------------------
def main():

    parser = argparse.ArgumentParser(prog=__program_name__, description=__description__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('diskname', type=str, help='Disk image file')
    parser.add_argument('file', type=str, nargs='?', default=None, help='file(s) to extract')
    parser.add_argument('--header', type=str, default=None, choices=['orix', 'tape'], help='prepend extracted file with header')
    parser.add_argument('--verbose', '-v', action='count', default=0, help='increase verbosity')
    parser.add_argument('--version', '-V', action='version', version='%%(prog)s v%s' % __version__)

    args = parser.parse_args()

    fs = ftdos(args.diskname, args.verbose)
    img_params = fs.validate(args.diskname)

    if img_params is None:
        eprint("Invalid disk image")
        sys.exit(1)

    fs.read_diskname()

    if args.verbose > 0:
        print('')
        print(args.diskname, ':')
        print('\tImage header')
        print('')
        print('Signature: ', fs.signature)
        print('DOS      : ', fs.dos)
        print('Faces    : ', fs.sides)
        print('Pistes   : ', fs.tracks)
        print('Secteurs : ', fs.sectors)
        print('Geometrie: ', fs.geometry)
        print('Offset   : ', fs.offset)
        print('')

    if fs.dos == 'FT-Dos':

        cat = fs.read_dir()

        if args.verbose > 1:
            print('')
            print('\tDisk informations')
            print('')
            fs.display_bitmap()
            print('')

        if args.verbose > 2:
            print('')
            pprint(cat)
            print('')

        if args.file is None:
            print('')
            print('\tDisk Catalog')
            print('')
            print('   VOLUME : %s (%s)' % (fs.diskname, fs.disktype))
            print('')
            fs._cat()
            print('')

        else:
            pattern = args.file.upper()

            for fn in cat.keys():
                if fnmatch.fnmatch(cat[fn]['stripped_name'], pattern):
                    raw = fs.read_file(fn)
                    pprint(raw)

                    with open(cat[fn]['stripped_name'], 'wb') as output:

                        if args.header == 'orix':
                            if (raw['type'] & 0x80 == 0x80) or raw['exec'] > 0:
                                output.write(b'\x01\x00ori\x01')

                                # cpu_mode
                                output.write(b'\x00')

                                # os_type: 0-Orix, 1-Sedoric, 2-Stratsed, 3-FTDos
                                output.write(b'\x03')

                                # reserved
                                output.write(b'\x00' * 5)

                                # type_of_file: b0-Basic, b1: machine
                                if raw['type'] & 0x80 == 0x80:
                                    output.write(chr(0b00000001))
                                elif raw['exec'] > 0x00:
                                    output.write(chr(0b00000010))

                                #
                                output.write(struct.pack('<H', raw['start']))
                                output.write(struct.pack('<H', raw['end']))
                                # output.write(struct.pack('<H',raw['start'] + raw['size']))
                                output.write(struct.pack('<H', raw['exec']))

                        elif args.header == 'tape':
                            output.write('\x16\x16\x16\x16\x24')
                            output.write('\xff\xff')

                            if raw['type'] & 0x80 == 0x80:
                                output.write('\x00')
                            else:
                                output.write('\x80')

                            output.write(chr(0x00))

                            output.write(struct.pack('>H', raw['start'] + raw['size']))
                            output.write(struct.pack('>H', raw['start']))

                            output.write(chr(len(fn)))
                            output.write(fn)
                            output.write('\x00')

                        output.write(raw['file'])

    else:
        eprint("Unknown DOS: ", fs.dos)
        sys.exit(2)


# ------------------------------------------------------------------------------
if __name__ == '__main__':
    main()
