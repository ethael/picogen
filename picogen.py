#!/usr/bin/env python3

# Copyright (c) 2020-2021
# Marián Mižik <marian@mizik.sk>, Martin Hlavňa <mato.hlavna@gmail.com>
#
# MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import sys
import glob
import argparse
import shutil
import re
import json
import unidecode
from enum import Enum
from datetime import datetime, timezone


class Log:
    """ Colored print functions for strings using universal ANSI escape seq """

    @staticmethod
    def err(message):
        sys.stderr.write('\x1b[1;31m' + message.strip() + '\x1b[0m' + '\n')

    @staticmethod
    def ok(message):
        sys.stdout.write('\x1b[1;32m' + message.strip() + '\x1b[0m' + '\n')

    @staticmethod
    def warn(message):
        sys.stderr.write('\x1b[1;33m' + message.strip() + '\x1b[0m' + '\n')

    @staticmethod
    def info(message):
        sys.stdout.write('\x1b[1;0m' + message.strip() + '\x1b[0m' + '\n')


class Protocol(Enum):
    """ enum with supported output protocols and helper methods """
    HTTP = 'http'
    GEMINI = 'gemini'

    @staticmethod
    def from_name(name):
        if name == 'http':
            return Protocol.HTTP
        elif name == 'gemini':
            return Protocol.GEMINI
        else:
            Log.err(f'Protocol name detection failed: Unknown protocol: {name}')

    def file_suffix(self):
        if self is Protocol.HTTP:
            return 'html'
        elif self is Protocol.GEMINI:
            return 'gmi'
        else:
            Log.err(f'File suffix detection failed: Unknown protocol: {self}')

    def scheme(self, is_ssl):
        if self is Protocol.HTTP:
            return 'https' if is_ssl else 'http'
        elif self is Protocol.GEMINI:
            return 'gemini'
        else:
            Log.err(f'Scheme detection failed: Unknown protocol: {self}')


def normalize_string(value):
    """ normalize string - remove any accents, replace spaces with hyphen and transform to lowercase """
    return unidecode.unidecode(value).lower().replace(" ", "-")


def read_file(path):
    """ read file 'path' and return file content """
    with open(path, 'r') as f:
        return f.read()


def write_to_file(path, value):
    """ create dir structure if needed and write 'value' to file 'path' """
    basedir = os.path.dirname(path)
    if not os.path.isdir(basedir):
        os.makedirs(basedir)
    with open(path, 'w') as f:
        f.write(value)


def parse_trailer(name, body, body_format):
    """ return the first paragraph from the post 'body' (to show in the indexes) """
    if body_format is Protocol.GEMINI:
        # for gemini, read until we find chars and then until blank line occurs
        result = ''
        for line in body.splitlines():
            if result and not line:
                return result
            elif not line:
                continue
            else:
                result = "\n".join((result, line))
    elif body_format is Protocol.HTTP:
        # for html, get the first <p> tag value
        try:
            from bs4 import BeautifulSoup
            return BeautifulSoup(body, 'html.parser').find_all('p')[0].text
        except (ImportError, IndexError) as e:
            Log.err(f'Summarize failed for {name}. Reason: {e}')
            return ''
    else:
        Log.err(f"Summarize failed for {name}. Reason: Unknown body format: {body_format}")


def fill(string_with_placeholders, **variables):
    """ find {{ x }} placeholders in the string source and replace them with variables """
    return re.sub(r'{{\s*([^}\s]+)\s*}}',
                  lambda m: str(variables.get(m.group(1), m.group(0))), string_with_placeholders)


def assemble_file_descriptor(path, cfg):
    """ assemble and return file descriptor dictionary for the supplied 'path' """
    descriptor = dict()
    # parse all annotations from the file beginning and add them to descriptor
    f = read_file(path)
    for m in re.finditer(r'\s*<!--\s*(.+?)\s*(?::\s*(.+?)\s*)?-->\s*|.+', f):
        if not m.group(1):
            break
        descriptor[m.group(1)] = m.group(2) if m.group(2) else ''
    # the rest is document body
    descriptor['body'] = f.split("\n", len(descriptor))[len(descriptor)]
    # add file name and extension
    descriptor['file_name'] = os.path.basename(path).split('.')[0]
    descriptor['file_ext'] = os.path.basename(path).split('.')[1]
    # add creation date if not declared and its rfc3339 variant (for atom feed)
    descriptor['date'] = descriptor['date'] if 'date' in descriptor else '1970-01-01'
    date_object = datetime.strptime(descriptor['date'], '%Y-%m-%d').astimezone()
    if 'custom_date_format' in cfg:
        descriptor['formatted_date'] = date_object.strftime(cfg['custom_date_format'])
    descriptor['rfc3339_date'] = date_object.isoformat()
    return descriptor


def convert(descriptor, protocol):
    """ convert body to the protocol format if current format is markdown"""
    if descriptor['file_ext'] in ['markdown', 'md']:
        name = f"{descriptor['file_name']}.{descriptor['file_ext']}"
        if protocol == Protocol.HTTP:
            import commonmark
            try:
                descriptor['body'] = commonmark.commonmark(descriptor['body'])
            except ImportError as e:
                Log.err(f"Convert md => html for {name} failed. {e}")
        elif protocol == Protocol.GEMINI:
            import md2gemini
            try:
                descriptor['body'] = md2gemini.md2gemini(descriptor['body'], links='newline')
            except ImportError as e:
                Log.err(f"Convert md => gemini for {name} failed. {e}")
        else:
            suffix = protocol.file_suffix()
            Log.err(f"Convert md => {suffix} for {name} failed: Unsupported format.")
    return descriptor


def fill_taxonomy_value_post_index(protocol, config, t_value, t_cfg, variables, templates, i_cfg, descriptors):
    """ fill taxonomy value posts index (tvpi), made of all values of specified taxonomy from files in content dir """
    t_value_variables = {
        'taxonomy_value': t_value,
        'taxonomy_value_lower': t_value.lower(),
        'taxonomy_value_normalized': normalize_string(t_value),
        'title': f"{t_cfg['title']} {t_value}",
    }
    item_outputs = []
    # sort and limit taxonomy values
    order_by = i_cfg['order_by'] if 'order_by' in i_cfg else 'date'
    reverse = False if 'order_direction' in i_cfg and i_cfg['order_direction'] == 'asc' else True
    descriptors = sorted(descriptors, reverse=reverse, key=lambda descriptor: descriptor[order_by])
    limit = int(i_cfg['limit']) if 'limit' in i_cfg else len(descriptors)
    # fill, summarize and save index item templates
    for d in descriptors[0:limit]:
        v = {**config, **variables, **t_value_variables, **d}
        v['body'] = fill(d['body'], **v)
        name = f"{d['file_name']}.{d['file_ext']}"
        v['summary'] = parse_trailer(name, v['body'], protocol)
        item_outputs.append(fill(templates[i_cfg['item_template']], **v))
    # merge index item outputs
    t_value_variables['body'] = ''.join(item_outputs)
    # fill user defined custom_variables
    v = {**config, **variables, **t_value_variables}
    if 'custom_variables' in i_cfg:
        for variable in i_cfg['custom_variables']:
            t_value_variables[variable] = fill(i_cfg['custom_variables'][variable], **v)
        v = {**config, **variables, **t_value_variables}
    return fill(templates[i_cfg['template']], **v)


def fill_taxonomy_value_index(config, t_cfg, templates, i_config, descriptors_by_taxonomy,
                              dynamic_vars, output_variables):
    """ fill taxonomy value posts index (tvi), made of all posts which define specified taxonomy and value """
    # taxonomy specific output variables to use in template
    t_id = t_cfg['id']
    t_values = list(descriptors_by_taxonomy[t_id].keys())
    t_variables = {
        'taxonomy_id': t_id,
        'taxonomy_title': t_cfg['title'],
        'title': t_cfg['title'],
    }
    if 'order_direction' in i_config:
        # sort index based on config preference (alphabetically vs. count) in specified direction
        reverse = False if 'order_direction' in i_config and i_config['order_direction'] == 'asc' else True
        order_by_count = True if 'order_by' in i_config and i_config['order_by'] == 'count' else False
        t_values = sorted(
            t_values,
            reverse=reverse,
            key=lambda t_value: len(descriptors_by_taxonomy[t_id][t_value]) if order_by_count else t_value
        )
    limit = i_config['limit'] if 'limit' in i_config else len(t_values)
    tv_bodies = []
    # generate body for every taxonomy value
    for tv in t_values[0:int(limit)]:
        t_value_variables = {
            'taxonomy_value': tv,
            'taxonomy_value_lower': tv.lower(),
            'taxonomy_value_normalized': normalize_string(tv),
            'taxonomy_value_posts_count': len(descriptors_by_taxonomy[t_id][tv])
        }
        # add whole another generated index of choice if user configured to inline some index under every taxonomy value
        if 'inlined_index_id' in i_config:
            variable_name = f"{t_id}_{i_config['inlined_index_id']}" f"_{normalize_string(tv)}"
            t_value_variables['taxonomy_value_posts_index'] = output_variables[variable_name]
        v = {**config, **t_variables, **t_value_variables, **dynamic_vars}
        tv_bodies.append(fill(templates[i_config['item_template']], **v))
    # join all generated bodies to one final result
    t_variables['body'] = ''.join(tv_bodies)
    v = {**config, **t_variables, **dynamic_vars}
    output = fill(templates[i_config['template']], **v)
    return output


def main():
    # declare input arguments
    parser = argparse.ArgumentParser(usage="""

    To initialize with functional demo page data for both http and gemini run:
    %(prog)s --init 
    
    To generate the resulting html or gemini run:
    %(prog)s --generate [FORMAT]

    To serve target locally using target/[FORMAT] as root dir run:
    %(prog)s --serve [FORMAT]
    
    """)
    mutex = parser.add_mutually_exclusive_group()
    mutex.add_argument(
        '-i',
        '--init',
        action='store_true',
        help="""
            Create directory/file structure with config and full demo page 
            (process includes automatic archive download)
        """
    )
    mutex.add_argument(
        '-s',
        '--serve',
        type=str,
        nargs=1,
        metavar='PROTOCOL',
        choices=['gemini', 'http'],
        help="Run local server and serve requested format. (http or gemini)"
    )
    parser.add_argument(
        '-p',
        '--port',
        type=int,
        help="Specify custom port for server to bind on (default is 8000)"
    )
    mutex.add_argument(
        '-g',
        '--generate',
        type=str,
        nargs='+',
        metavar='PROTOCOL',
        choices=['gemini', 'http'],
        help="""
            Generate pages to requested format and save to 'target/[FORMAT]' 
            directory. (http and/or gemini)
        """
    )

    # parse arguments
    args = parser.parse_args()
    # if no arguments given, show help
    if len(sys.argv) == 1:
        parser.print_help()
        exit(0)

    # business logic for --init
    if args.init:
        import urllib.request as ur
        from zipfile import ZipFile
        Log.info('Downloading archive with initialization files')
        ur.urlretrieve('https://github.com/ethael/picogen/raw/main/init.zip', 'init.zip')
        with ZipFile('init.zip', 'r') as zipFile:
            Log.info(f'Unpacking in current directory ({os.path.abspath(os.getcwd())})')
            zipFile.extractall()
            Log.ok('Initialization successful')
            os.remove('init.zip')

    # business logic for --serve
    if args.serve:
        port = args.port or 8000
        if 'http' in args.serve:
            import http.server
            import socketserver as ss
            ss.TCPServer.allow_reuse_address = True
            os.chdir('target/html')
            with ss.TCPServer(("", port), http.server.SimpleHTTPRequestHandler) as httpd:
                Log.ok(f'serving data from target/html on port {port}')
                httpd.serve_forever()
        if 'gemini' in args.serve:
            from jetforce import GeminiServer, StaticDirectoryApplication
            from jetforce.app.composite import CompositeApplication
            app = CompositeApplication({"localhost": StaticDirectoryApplication(root_directory="target/gmi")})
            Log.ok('serving data from target/gmi')
            GeminiServer(app, port=port).run()

    # business logic for --generate
    if args.generate:
        cfg = None
        try:
            # clean target directory
            if os.path.isdir('target'):
                shutil.rmtree('target')
                os.makedirs('target')
            # load configuration
            cfg = json.loads(read_file('config.json'))
        except FileNotFoundError as e:
            Log.err(f"Initial filesystem check failed: {e}")
            Log.err(f"Run picogen with --init to execute filesystem structure setup with demo data")
            exit(1)

        # run business logic for --generate for every type (http, gemini)
        # NOTE variable prefix "t_" stands for "taxonomy_"
        for item in args.generate:

            # STEP 1. INITIALIZE

            # define generation type specific variables
            protocol = Protocol.from_name(item)
            suffix = protocol.file_suffix()
            scheme = protocol.scheme(cfg['ssl_enabled'])
            # copy static files to target directory
            shutil.copytree(f'static/{suffix}', f'target/{suffix}')
            # load templates
            templates = dict()
            for filepath in glob.glob(f'templates/{suffix}/*.*'):
                filename = os.path.basename(filepath).split('.')[0]
                templates[filename] = read_file(filepath)
            # if template has parent, merge them together (1 level deep for now)
            for template_name in list(templates):
                if '_' in template_name:
                    child_and_parent = template_name.split('_')
                    parent_value = templates[child_and_parent[1]]
                    child_value = templates.pop(template_name)
                    templates[child_and_parent[0]] = fill(parent_value, body=child_value)
            # declare initial dynamic variables (generated by picogen)
            dynamic_vars = dict()
            dynamic_vars['scheme'] = scheme
            dynamic_vars['current_year'] = datetime.now().year
            dynamic_vars['rfc3339_now'] = datetime.now(timezone.utc).astimezone().isoformat()
            # optionally load page views for posts if file available (file format is file:views on every line)
            page_views = dict()
            if 'page_views_file' in cfg:
                for line in read_file(cfg['page_views_file']).splitlines():
                    parts = line.split(sep=":")
                    page_views[parts[0]] = int(parts[1])

            # STEP 2. ASSEMBLE FILE DESCRIPTORS (FILES IN CONTENT DIR PARSED TO DICTS)

            # array to store all generated file descriptors for later template filling
            descriptors = []
            # dict where descriptor is copied under all values of all taxonomies declared in the file headers
            # it will be used for later taxonomy value indexes and taxonomy value posts indexes generation
            descriptors_by_t_value = dict()

            for root, dirs, files in os.walk('content'):
                # recursively travers content folder. assemble and save descriptor for every file
                for f in files:
                    # assemble descriptor
                    d = assemble_file_descriptor(os.path.join(root, f), cfg)
                    # don't process this file further if marked as draft
                    if 'draft' in d:
                        continue
                    # don't process if it isn't markdown nor protocol native file
                    if d['file_ext'] not in ['markdown', 'md', suffix]:
                        continue
                    # assemble correct target path and relative path
                    if d['file_name'] == 'index':
                        d['target_path'] = os.path.join(f'target/{suffix}', root[8:], f'index.{suffix}')
                        d['relative_path'] = os.path.join(cfg['base_path'], root[8:], f'index.{suffix}')
                        d['relative_dir_path'] = os.path.join(cfg['base_path'], root[8:])
                    else:
                        d['target_path'] = os.path.join(f'target/{suffix}', root[8:], d['file_name'], f'index.{suffix}')
                        d['relative_path'] = os.path.join(cfg['base_path'], root[8:], d['file_name'], f'index.{suffix}')
                        d['relative_dir_path'] = os.path.join(cfg['base_path'], root[8:], d['file_name'])
                    d['page_views'] = page_views[d['relative_dir_path']] if d['relative_dir_path'] in page_views else 0
                    # save descriptor under every value of every declared taxonomy
                    t_template = None
                    if 'taxonomies' in cfg:
                        for t in cfg['taxonomies']:
                            t_id = t['id']
                            if t_id not in descriptors_by_t_value:
                                descriptors_by_t_value[t_id] = dict()
                            if t_id in d:
                                if 'document_template' in t:
                                    if t_template:
                                        Log.warn('Multiple applicable taxonomy templates found for {file_path} ')
                                    t_template = t['document_template']
                                for t_value in d[t_id].split(','):
                                    t_value = t_value.strip()
                                    if t_value not in descriptors_by_t_value[t_id]:
                                        descriptors_by_t_value[t_id][t_value] = []
                                    descriptors_by_t_value[t_id][t_value].append(d)
                    # choose correct template
                    if 'template' not in d:
                        if t_template:
                            d['template'] = t_template
                        else:
                            Log.warn(f"No template specified for {d['target_path']}. Using default")
                            d['template'] = cfg['default_template']
                    # convert body from markdown to protocol specific format
                    d = convert(d, protocol)
                    # save descriptor for later file generation
                    descriptors.append(d)

            # STEP 3. ASSEMBLE INDEX DESCRIPTORS

            # generation configs for those taxonomy value indexes (tvpi) which are provided as generated variables
            tvpi_as_variable_cfgs = []
            # generation configs for those taxonomy value posts indexes (tvi) which are provided as generated variables
            tvi_as_variable_cfgs = []
            # generation configs for taxonomy value indexes (tvpi) which are exported to files
            tvpi_as_file_cfgs = []
            # generation configs for taxonomy value posts indexes (tvi) that are exported to files
            tvi_as_file_cfgs = []
            if 'taxonomies' in cfg:
                for t in cfg['taxonomies']:
                    if 'value_posts_indexes' in t:
                        # inspect declared indexes for taxonomy
                        for vpi in t['value_posts_indexes']:
                            i_cfg = {'taxonomy_cfg': t, 'index_cfg': vpi}
                            if 'output_type' in vpi and vpi['output_type'] == 'file':
                                tvpi_as_file_cfgs.append(i_cfg)
                            elif 'output_type' in vpi and vpi['output_type'] == 'variable':
                                tvpi_as_variable_cfgs.append(i_cfg)
                    if 'value_indexes' in t:
                        # inspect declared value lists for taxonomy
                        for vi in t['value_indexes']:
                            i_cfg = {'taxonomy_cfg': t, 'index_cfg': vi}
                            if 'output_type' in vi and vi['output_type'] == 'file':
                                tvi_as_file_cfgs.append(i_cfg)
                            elif 'output_type' in vi and vi['output_type'] == 'variable':
                                tvi_as_variable_cfgs.append(i_cfg)

            # STEP 4. GENERATE INDEXES WHICH ARE PROVIDED AS GENERATED VARIABLES IN STEP 5 AND STEP 6

            generated_variables = dict()
            for tvpi_cfg in tvpi_as_variable_cfgs:
                t_cfg = tvpi_cfg['taxonomy_cfg']
                t_id = t_cfg['id']
                i_cfg = tvpi_cfg['index_cfg']
                # taxonomy specific output variables to use in template
                t_variables = {'taxonomy_id': t_id, 'taxonomy_title': t_cfg['title'], 'title': t_cfg['title'], }
                # iterate over taxonomy values
                for t_value in descriptors_by_t_value[t_id]:
                    output = fill_taxonomy_value_post_index(protocol, cfg, t_value, t_cfg,
                                                            {**t_variables, **generated_variables, **dynamic_vars},
                                                            templates, i_cfg, descriptors_by_t_value[t_id][t_value])
                    normalized_value = normalize_string(t_value)
                    variable_name = f"{t_id}_{i_cfg['id']}"
                    if normalized_value:
                        variable_name += f"_{normalized_value}"
                    generated_variables[variable_name] = output
                    Log.ok(f"Generated {variable_name} taxonomy index variable")
            for tvi_cfg in tvi_as_variable_cfgs:
                t_cfg = tvi_cfg['taxonomy_cfg']
                i_cfg = tvi_cfg['index_cfg']
                output = fill_taxonomy_value_index(cfg, t_cfg, templates, i_cfg, descriptors_by_t_value,
                                                   dynamic_vars, generated_variables)
                variable_name = f"{t_cfg['id']}_{i_cfg['id']}"
                generated_variables[variable_name] = output
                Log.ok(f"Generated {variable_name} taxonomy value list variable")

            #  STEP 5. GENERATE INDEXES WHICH ARE EXPORTED TO FILES

            for tvpi_cfg in tvpi_as_file_cfgs:
                t_cfg = tvpi_cfg['taxonomy_cfg']
                t_id = t_cfg['id']
                i_cfg = tvpi_cfg['index_cfg']
                # taxonomy specific output variables to use in template
                t_variables = {
                    'taxonomy_id': t_id,
                    'taxonomy_title': t_cfg['title'],
                    'title': t_cfg['title'],
                }
                # iterate over taxonomy values
                for t_value in descriptors_by_t_value[t_id]:
                    output = fill_taxonomy_value_post_index(protocol, cfg, t_value, t_cfg,
                                                            {**t_variables, **dynamic_vars, **generated_variables},
                                                            templates, i_cfg, descriptors_by_t_value[t_id][t_value])
                    # use custom output_path if specified, otherwise use default taxonomy-based path
                    if 'output_path' in i_cfg:
                        target_path = os.path.join(
                            f"target/{suffix}",
                            f'{i_cfg["output_path"]}'
                        )
                    else:
                        target_path = os.path.join(
                            f"target/{suffix}/{t_cfg['id']}",
                            normalize_string(t_value) if t_value else '',
                            f'{i_cfg["id"]}.{i_cfg["output_suffix"] if "output_suffix" in i_cfg else suffix}'
                        )
                    write_to_file(target_path, output)
                    Log.ok(f"Generated {t_cfg['id']} {i_cfg['id']} index => {target_path}")

            for tvi_cfg in tvi_as_file_cfgs:
                t_cfg = tvi_cfg['taxonomy_cfg']
                t_id = t_cfg['id']
                i_cfg = tvi_cfg['index_cfg']
                output = fill_taxonomy_value_index(cfg, t_cfg, templates, i_cfg, descriptors_by_t_value,
                                                   dynamic_vars, generated_variables)
                target_path = os.path.join(
                    f"target/{suffix}/{t_id}",
                    f'{i_cfg["id"]}.{i_cfg["output_suffix"] if "output_suffix" in i_cfg else suffix}'
                )
                write_to_file(target_path, output)
                Log.ok(f"Generated {t_cfg['id']} {i_cfg['id']} value_list => {target_path}")

            # STEP 6. GENERATE STANDARD FILES FROM CONTENT DIRECTORY

            for d in descriptors:
                d['body'] = fill(d['body'], **d, **cfg, **dynamic_vars, **generated_variables)
                name = f"{d['file_name']}.{d['file_ext']}"
                d['summary'] = parse_trailer(name, d['body'], protocol)
                template = templates[d['template']]
                write_to_file(d['target_path'], fill(template, **d, **cfg, **dynamic_vars, **generated_variables))
                Log.ok(f"Generated {d['file_name']}.{d['file_ext']} => {d['target_path']}")


if __name__ == '__main__':
    main()
