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
from enum import Enum
from datetime import datetime, timezone
from signal import signal, SIGINT


class Log:
    """ Colored print functions for strings using universal ANSI escape seq """

    @staticmethod
    def err(message, end='\n'):
        sys.stderr.write('\x1b[1;31m' + message.strip() + '\x1b[0m' + end)

    @staticmethod
    def ok(message, end='\n'):
        sys.stdout.write('\x1b[1;32m' + message.strip() + '\x1b[0m' + end)

    @staticmethod
    def warn(message, end='\n'):
        sys.stderr.write('\x1b[1;33m' + message.strip() + '\x1b[0m' + end)

    @staticmethod
    def info(message, end='\n'):
        sys.stdout.write('\x1b[1;0m' + message.strip() + '\x1b[0m' + end)


class Protocol(Enum):
    """ enum with supported output protocols and helpder methods """
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


def format_to_rfc3339(value):
    """ format 'value' (string in format: yyyy-mm-dd) to rfc3339 string """
    return datetime.strptime(value, '%Y-%m-%d').astimezone().isoformat()


def read_file(path):
    """ read file 'path' and return file content """
    with open(path, 'r') as f:
        return f.read()


def normalize_string(s):
    """ normalize string - remove any accents, replace spaces with hyphen and lowercase """
    import unidecode
    return unidecode.unidecode(s).lower().replace(" ", "-")


def write_file(path, data):
    """ create dir structure if needed and write 'data' to file 'path' """
    basedir = os.path.dirname(path)
    if not os.path.isdir(basedir):
        os.makedirs(basedir)
    with open(path, 'w') as f:
        f.write(data)


def summarize(body, body_format):
    """ return the first paragraph from the article 'body' """
    if body_format is Protocol.GEMINI:
        # for gemini, read until we find chars and then until blank line occurs
        result = ''
        for line in body.splitlines():
            if result and not line:
                return result;
            elif not line:
                continue
            else:
                result = "\n".join((result, line))
    elif body_format is Protocol.HTTP:
        # for html, get the first <p> tag value
        try:
            from bs4 import BeautifulSoup
            return BeautifulSoup(body, 'html.parser').find_all('p')[0].text
        except ImportError as e:
            Log.err(f'Summarize failed: {e}')
        except IndexError as e:
            Log.err(f'Summarize failed: {e}')
            return ''
    else:
        Log.err(f"Summarize failed: Unknown body format: {body_format}")


def fill(tpl, **variables):
    """ find {{ x }} placeholders in 'tpl' & replace with variable """
    return re.sub(r'{{\s*([^}\s]+)\s*}}',
                  lambda m: str(variables.get(m.group(1), m.group(0))), tpl)


def convert_and_fill_body(descriptor, protocol, **variables):
    """ replace placeholders in body with variables & convert to protocol format """
    descriptor['body'] = fill(descriptor['body'], **variables)
    # convert body if necessary
    if descriptor['file_ext'] in ['markdown', 'md']:
        if protocol == Protocol.HTTP:
            try:
                import commonmark as cm
                descriptor['body'] = cm.commonmark(descriptor['body'])
            except ImportError as e:
                file_name = descriptor['file_name']
                Log.err(f"Convert md => html failed: {file_name}. {e}")
        elif protocol == Protocol.GEMINI:
            try:
                from md2gemini import md2gemini
                descriptor['body'] = md2gemini(descriptor['body'], links='newline')
            except ImportError as e:
                file_name = descriptor['file_name']
                Log.err(f"Convert md => gemini failed: {file_name}. {e}")
        else:
            suffix = protocol.file_suffix()
            Log.err(f"Convert md => {suffix} failed: Unsupported format.")
    # generate summary for finalized body
    descriptor['summary'] = summarize(descriptor['body'], protocol)

    return descriptor


def assemble_file_descriptor(path):
    """ assemble and return descriptor dict for the supplied 'path' """
    descriptor = {}
    # parse all annotations from the file beginning and add them to descriptor
    f = read_file(path)
    for m in re.finditer(r'\s*<!--\s*(.+?)\s*:\s*(.+?)\s*-->\s*|.+', f):
        if not m.group(1):
            break
        descriptor[m.group(1)] = m.group(2)
    # the rest is document body
    descriptor['body'] = f.split("\n", len(descriptor))[len(descriptor)]
    # add file name and extension
    descriptor['file_name'] = os.path.basename(path).split('.')[0]
    descriptor['file_ext'] = os.path.basename(path).split('.')[1]
    # add creation date if not declared and its rfc3339 variant (for atom) 
    if 'date' not in descriptor:
        descriptor['date'] = '1970-01-01'
    descriptor['rfc3339_date'] = format_to_rfc3339(descriptor['date'])

    return descriptor


def fill_index(protocol, config, taxonomy_config, templates, tid, tvalue, index_config, taxonomy_variables,
               descriptors_by_taxonomies,
               dynamic_vars, output_variables):
    term_variables = {
        'taxonomy_value': tvalue,
        'taxonomy_value_lower': tvalue.lower(),
        'taxonomy_value_normalized': normalize_string(tvalue),
        'title': f"{taxonomy_config['title']} {tvalue}",
    }
    item_outputs = []
    # sort and limit posts
    order_by = index_config['order_by'] if 'order_by' in index_config else 'date'
    reverse = False if 'order_direction' in index_config and index_config['order_direction'] == 'asc' \
        else True
    dbt = sorted(descriptors_by_taxonomies[tid][tvalue], key=lambda d: d[order_by], reverse=reverse)
    limit = int(index_config['limit']) if 'limit' in index_config else len(dbt)
    # convert, fill and save item templates
    for d in dbt[0:limit]:
        v = {**config, **taxonomy_variables, **term_variables, **output_variables, **dynamic_vars, **d}
        d = convert_and_fill_body(d, protocol, **v)
        v = {**config, **taxonomy_variables, **term_variables, **output_variables, **dynamic_vars, **d}
        item_output = fill(templates[index_config['item_template']], **v)
        item_outputs.append(item_output)
    # merge item outputs
    term_variables['body'] = ''.join(item_outputs)
    v = {**config, **taxonomy_variables, **term_variables, **output_variables, **dynamic_vars}
    if 'custom_variables' in index_config:
        for variable in index_config['custom_variables']:
            term_variables[variable] = fill(index_config['custom_variables'][variable], **v)
        v = {**config, **taxonomy_variables, **term_variables, **output_variables, **dynamic_vars}
    return fill(templates[index_config['template']], **v)


def fill_value_list(config,
                    taxonomy_config,
                    templates,
                    tid,
                    value_list_config,
                    descriptors_by_taxonomies,
                    dynamic_vars,
                    output_variables):
    # taxonomy specific output variables to use in template
    taxonomy_variables = {
        'taxonomy_id': tid,
        'taxonomy_title': taxonomy_config['title'],
        'title': taxonomy_config['title'],
    }
    taxonomy_keys = list(descriptors_by_taxonomies[tid].keys())
    if 'order_direction' in value_list_config:
        # sort index alphabetically in specified direction
        reverse = False if 'order_direction' in value_list_config \
                           and value_list_config['order_direction'] == 'asc' \
            else True
        sort_by_count = True if 'order_by' in value_list_config \
                                and value_list_config['order_by'] == 'count' \
            else False
        taxonomy_keys = sorted(
            taxonomy_keys,
            reverse=reverse,
            key=lambda key: len(descriptors_by_taxonomies[tid][key]) if sort_by_count else key)
    limit = value_list_config['limit'] if 'limit' in value_list_config else len(taxonomy_keys)
    item_outputs = []
    for term in taxonomy_keys[0:int(limit)]:
        term_variables = {
            'taxonomy_value': term,
            'taxonomy_value_lower': term.lower(),
            'taxonomy_value_normalized': normalize_string(term),
            'taxonomy_value_posts_count': len(descriptors_by_taxonomies[tid][term])
        }
        if 'inlined_index_id' in value_list_config:
            variable_name = f"{taxonomy_config['id']}_{value_list_config['inlined_index_id']}" \
                            f"_{normalize_string(term)}"
            Log.warn(f'PIK: {variable_name}')
            term_variables['taxonomy_value_list'] = output_variables[variable_name]
        v = {**config, **taxonomy_variables, **term_variables, **dynamic_vars}
        item_output = fill(templates[value_list_config['item_template']], **v)
        item_outputs.append(item_output)
    taxonomy_variables['body'] = ''.join(item_outputs)
    v = {**config, **taxonomy_variables, **dynamic_vars}
    output = fill(templates[value_list_config['template']], **v)
    return output


def main():
    # declare input arguments
    parser = argparse.ArgumentParser(usage="""

    To initialize with functional demo page data for both http and gemini run:
    %(prog)s --init http gemini

    To generate both http and gemini with support for tags and comments run:
    %(prog)s --generate http gemini --enable-comments --enable-tags

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
    parser.add_argument(
        '-c',
        '--enable-comments',
        action='store_true',
        help="Enable support for comments. (only for 'generate')"
    )
    parser.add_argument(
        '-t',
        '--enable-tags',
        action='store_true',
        help="Enable support for tags. (only for 'generate')"
    )

    # parse arguments
    args = parser.parse_args()
    # if no arguments given, show help
    if len(sys.argv) == 1:
        parser.print_help()
        exit(0)
    # do not allow use of -c and -t for 'serve' option
    if args.serve and (args.enable_comments or args.enable_tags):
        Log.err("--enable-comments (-c) or --enable-tags (-t) can not be used with --serve (-s)")
        exit(1)
    # do not allow use of -p for 'generate' option
    if args.generate and args.port:
        Log.err("--port (-p) can not be used with --generate (-g)")
        exit(1)
    # do not allow use of -p -t and -c for 'init' option
    if args.init and (args.port or args.enable_comments or args.enable_tags):
        Log.err("--port (-p) --enable-comments (-c) --enable-tags (-t) can not be used with --init (-i)")
        exit(1)

    # business logic for --init
    if args.init:
        import urllib.request as ur
        from zipfile import ZipFile
        Log.info('Downloading archive with initialization files')
        ur.urlretrieve('https://mizik.eu/picogen/init.zip', 'init.zip')
        with ZipFile('init.zip', 'r') as zipFile:
            Log.info(f'Unpacking in current directory ({os.path.abspath(os.getcwd())})')
            zipFile.extractall()
            Log.ok('Initialization successfull')
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
            app = CompositeApplication({
                "localhost": StaticDirectoryApplication(root_directory="target/gmi"),
            })
            Log.ok('serving data from target/gmi')
            GeminiServer(app, port=port).run()

    # business logic for --generate
    if args.generate:
        try:
            # clean target directory 
            if os.path.isdir('target'):
                shutil.rmtree('target')
                os.makedirs('target')
            # load config.json 
            config = json.loads(read_file('config.json'))
        except FileNotFoundError as e:
            Log.err(f"Initial filesystem check failed: {e}")
            Log.err(f"Run picogen with --init to execute filesystem structure setup")
            exit(1)

        # run business logic for --generate for every type (http, gemini)
        for item in args.generate:
            ##############################
            #         INITIALIZE         #
            ##############################

            # define generation type specific variables
            protocol = Protocol.from_name(item)
            suffix = protocol.file_suffix()
            scheme = protocol.scheme(config['ssl_enabled'])
            # copy static files to target directory
            shutil.copytree(f'static/{suffix}', f'target/{suffix}')
            # load templates
            templates = dict()
            for filepath in glob.glob(f'templates/{suffix}/*.*'):
                filename = os.path.basename(filepath).split('.')[0]
                templates[filename] = read_file(filepath)
            # if template has parent, merge them together (1 level deep for now)
            for tpl_name in list(templates):
                if '_' in tpl_name:
                    child_and_parent = tpl_name.split('_')
                    parent_value = templates[child_and_parent[1]]
                    child_value = templates.pop(tpl_name)
                    child_value = fill(parent_value, body=child_value)
                    templates[child_and_parent[0]] = child_value
                    # declare initial dynamic variables
            dynamic_vars = dict()
            dynamic_vars['scheme'] = scheme
            dynamic_vars['current_year'] = datetime.now().year
            dynamic_vars['rfc3339_now'] = datetime.now(timezone.utc).astimezone().isoformat()

            ##############################
            #  ASSEMBLE FILE DESCRIPTORS #
            ##############################

            # array to store all generated descriptors for later file generation
            descriptors = []
            # dict where every descriptor is copied under every value of every 
            # taxonomy it declares. for later indexes generations 
            descriptors_by_taxonomies = dict()
            pageviews = dict()
            if 'pageviews_file' in config:
                # if user provided optional pagecounts_file load pageviews
                f = read_file(config['pageviews_file'])
                for line in f.splitlines():
                    parts = line.split(sep=":")
                    pageviews[parts[0]] = int(parts[1])

            for root, subdirs, files in os.walk('content'):
                # recursively travers content folder and assemble&save descriptors
                for f in files:
                    # assemble descriptor
                    file_path = os.path.join(root, f)
                    d = assemble_file_descriptor(file_path)
                    # don't process this file further if marked as draft
                    if 'draft' in d:
                        continue
                    # don't process if it isn't markdown nor protocol native file
                    if d['file_ext'] not in ['markdown', 'md', suffix]:
                        continue
                    # assemble correct target path and relative path 
                    if d['file_name'] == 'index':
                        d['target_path'] = os.path.join(f'target/{suffix}', root[8:], f'index.{suffix}')
                        d['relative_path'] = os.path.join(config['base_path'], root[8:], f'index.{suffix}')
                        d['relative_dir_path'] = os.path.join(config['base_path'], root[8:])
                    else:
                        d['target_path'] = os.path.join(f'target/{suffix}', root[8:], d['file_name'], f'index.{suffix}')
                        d['relative_path'] = os.path.join(config['base_path'], root[8:], d['file_name'],
                                                          f'index.{suffix}')
                        d['relative_dir_path'] = os.path.join(config['base_path'], root[8:], d['file_name'])
                    d['pageviews'] = 0
                    if d['relative_dir_path'] in pageviews:
                        d['pageviews'] = pageviews[d['relative_dir_path']]
                    # save descriptor under every value of every declared taxonomy
                    if 'taxonomies' in config:
                        taxonomy_template = None
                        for t in config['taxonomies']:
                            tid = t['id']
                            if tid not in descriptors_by_taxonomies:
                                descriptors_by_taxonomies[tid] = dict()
                            if tid in d:
                                if 'document_template' in t:
                                    if taxonomy_template:
                                        Log.warn('Multiple applicable taxonomy templates found for {file_path} ')
                                    taxonomy_template = t['document_template']
                                for value in d[tid].split(','):
                                    value = value.strip()
                                    if value not in descriptors_by_taxonomies[tid]:
                                        descriptors_by_taxonomies[tid][value] = []
                                    descriptors_by_taxonomies[tid][value].append(d)
                    # choose correct template
                    if 'template' not in d:
                        if taxonomy_template:
                            d['template'] = taxonomy_template
                        else:
                            Log.warn(f"No template specified for {d['target_path']}. Using default")
                            d['template'] = config['default_template']
                    # save descriptor for later file generation
                    descriptors.append(d)

            ##############################
            # GENERATE TAXONOMY INDEXES  #
            ##############################
            # descriptors for indexes that are built as variables
            index_list_variable_descriptors = []
            # descriptors for value_lists that are built as variables
            value_list_variable_descriptors = []
            # descriptors for indexes that are built as files
            index_list_file_descriptors = []
            # descriptors for value_lists that are built as files
            value_list_file_descriptors = []
            # generated taxonomy variables (indexes and value_lists)
            output_variables = dict()
            if 'taxonomies' in config:
                for t in config['taxonomies']:
                    tid = t['id']
                    # taxonomy specific variables
                    if 'indexes' in t:
                        # inspect declared indexes for taxonomy
                        for i in t['indexes']:
                            index_list_descriptor = {
                                'taxonomy': t,
                                'index': i
                            }
                            if 'output_type' in i and i['output_type'] == 'file':
                                index_list_file_descriptors.append(index_list_descriptor)
                            elif 'output_type' in i and i['output_type'] == 'variable':
                                index_list_variable_descriptors.append(index_list_descriptor)
                    if 'value_lists' in t:
                        # inspect declared value lists for taxonomy
                        for vl in t['value_lists']:
                            value_list_descriptor = {
                                'taxonomy': t,
                                'value_list': vl
                            }
                            if 'output_type' in vl and vl['output_type'] == 'file':
                                value_list_file_descriptors.append(value_list_descriptor)
                            elif 'output_type' in vl and vl['output_type'] == 'variable':
                                value_list_variable_descriptors.append(value_list_descriptor)

            ##############################
            #     GENERATE VARIABLES     #
            ##############################
            # first we need to generate all taxonomy indexes that outputs variable
            for ilvd in index_list_variable_descriptors:
                tid = ilvd['taxonomy']['id']
                taxonomy_config = ilvd['taxonomy']
                index_config = ilvd['index']
                # taxonomy specific output variables to use in template
                taxonomy_variables = {
                    'taxonomy_id': tid,
                    'taxonomy_title': taxonomy_config['title'],
                    'title': taxonomy_config['title'],
                }
                # iterate over taxonomy values
                for tvalue in descriptors_by_taxonomies[tid]:
                    output = fill_index(
                        protocol,
                        config,
                        taxonomy_config,
                        templates,
                        tid,
                        tvalue,
                        index_config,
                        taxonomy_variables,
                        descriptors_by_taxonomies,
                        dynamic_vars,
                        output_variables
                    )
                    variable_name = f"{taxonomy_config['id']}_{index_config['id']}_{normalize_string(tvalue)}"
                    output_variables[variable_name] = output
                    Log.ok(f"Generated {variable_name} taxonomy index variable")
            # now we have all index variables we may possibly need. Let's do same with the value_lists
            for vlvd in value_list_variable_descriptors:
                tid = vlvd['taxonomy']['id']
                taxonomy_config = vlvd['taxonomy']
                value_list_config = vlvd['value_list']
                output = fill_value_list(
                    config,
                    taxonomy_config,
                    templates,
                    tid,
                    value_list_config,
                    descriptors_by_taxonomies,
                    dynamic_vars,
                    output_variables
                )
                variable_name = f"{taxonomy_config['id']}_{value_list_config['id']}"
                output_variables[variable_name] = output
                Log.ok(f"Generated {variable_name} taxonomy value list variable")
            ##############################
            #       GENERATE FILES       #
            ##############################
            # all variables has been generated. Generate files for indexes
            for ilfd in index_list_file_descriptors:
                tid = ilfd['taxonomy']['id']
                taxonomy_config = ilfd['taxonomy']
                index_config = ilfd['index']
                # taxonomy specific output variables to use in template
                taxonomy_variables = {
                    'taxonomy_id': tid,
                    'taxonomy_title': taxonomy_config['title'],
                    'title': taxonomy_config['title'],
                }
                # iterate over taxonomy values
                for tvalue in descriptors_by_taxonomies[tid]:
                    output = fill_index(
                        protocol,
                        config,
                        taxonomy_config,
                        templates,
                        tid,
                        tvalue,
                        index_config,
                        taxonomy_variables,
                        descriptors_by_taxonomies,
                        dynamic_vars,
                        output_variables
                    )
                    target_path = os.path.join(
                        f"target/{suffix}/{taxonomy_config['id']}",
                        normalize_string(tvalue) if tvalue else '',
                        f'{index_config["id"]}.{index_config["output_suffix"] if "output_suffix" in index_config else suffix}'
                    )
                    write_file(target_path, output)
                    Log.ok(f"Generated {taxonomy_config['id']} {index_config['id']} index => {target_path}")
            # value list files
            for vlfd in value_list_file_descriptors:
                tid = vlfd['taxonomy']['id']
                taxonomy_config = vlfd['taxonomy']
                value_list_config = vlfd['value_list']
                output = fill_value_list(
                    config,
                    taxonomy_config,
                    templates,
                    tid,
                    value_list_config,
                    descriptors_by_taxonomies,
                    dynamic_vars,
                    output_variables
                )
                target_path = os.path.join(
                    f"target/{suffix}/{tid}",
                    f'{value_list_config["id"]}.{value_list_config["output_suffix"] if "output_suffix" in value_list_config else suffix}'
                )
                write_file(target_path, output)
                Log.ok(f"Generated {taxonomy_config['id']} {value_list_config['id']} value_list => {target_path}")
            # and finally, generate post files
            for d in descriptors:
                d = convert_and_fill_body(d, protocol, **d, **config, **dynamic_vars, **output_variables)
                tpl = templates[d['template']]
                write_file(
                    d['target_path'],
                    fill(tpl, **d, **config, **dynamic_vars, **output_variables)
                )
                Log.ok(f"Generated {d['file_name']}.{d['file_ext']} => {d['target_path']}")

            # TODO make taxonomy placeholders clickable
            # TODO custom target_path (or alias) in headers/index config (so blog feed.xml will be at root)


if __name__ == '__main__':
    main()
