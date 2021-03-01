import csv
import os
from os.path import exists, join

import json

from capreolus.extractor import get_file_name
from capreolus.utils.loginit import get_logger

from capreolus.registry import ModuleBase, RegisterableModule, Dependency, PACKAGE_PATH
import requests

logger = get_logger(__name__)

class EntityLinking(ModuleBase, metaclass=RegisterableModule):
    """the module base class"""

    module_type = "entitylinking"

class AmbiverseNLU(EntityLinking):
    name = 'ambiversenlu'
    server = open(PACKAGE_PATH / "data" / "ambiversenlu" / "server", 'r').read().replace("\n", "")  # TODO set the ambiverseNLU server here
    yagodescription_dir = '/GW/D5data-11/ghazaleh/search_ranking_data/yago_description_20180120/'
    #PACKAGE_PATH / 'data' / 'yago_descriptions' #TODO set YAGO description path

    dependencies = {
        "benchmark": Dependency(module="benchmark"),
    }

    entity_descriptions = {}

    @staticmethod
    def config():
        extractConcepts = True ## TODO: let's get the pipeline as input (later when I implemented that part).
        descriptions = "YAGO_long_short"
        pipeline = "ENTITY_CONCEPT_JOINT_LINKING" #"ENTITY_CONCEPT_SEPARATE_LINKING", "ENTITY_CONCEPT_SALIENCE_STANFORD", "ENTITY_CONCEPT_SALIENCE" "ENTITY_CONCEPT_SPOTTING_SEPARATE_DISAMBIGUATION" "ENTITY_CONCEPT_SPOTTING_JOINT_DISAMBIGUATION"
        typerestriction = False #if true we restrict movies, books, travel, food named entities

    def get_extracted_entities_cache_path(self):
        # logger.debug(f"entities cache path: {self.get_cache_path()}")
        return self.get_cache_path() / 'entities'

    def get_benchmark_domain(self):
        return self['benchmark'].domain

    def get_benchmark_querytype(self):
        return self['benchmark'].query_type

    def get_benchmark_name(self):
        return self['benchmark'].name

    def get_benchmark_cache_dir(self):
        return self['benchmark'].get_cache_path()

    @property
    def pipeline(self):
        return self.cfg["pipeline"]

    def extract_entities(self, textid, text):
        if self.get_benchmark_querytype() == 'entityprofile':  # This is only using PES20 benchmark which we are not going to release
            raise ValueError("wrong usage of incorporate entities. Do not use it with querytype 'entityprofile'")

        out_dir = self.get_extracted_entities_cache_path()
        if exists(join(out_dir, get_file_name(textid, self.get_benchmark_name(), self.get_benchmark_querytype()))):
            entities = self.get_all_entities(textid)
            # we want to only read entity descriptions which we need, so we initialize this here
            for e in entities["NE"]:
                self.entity_descriptions[e] = ""
            for e in entities["C"]:
                self.entity_descriptions[e] = ""
            return

        os.makedirs(out_dir, exist_ok=True)

        annotationsNE = []
        annotationsC = []
        annotationsEither = []
        if self.pipeline in ["ENTITY_CONCEPT_JOINT_LINKING", "ENTITY_CONCEPT_SEPARATE_LINKING"]:
            # we want to remove the brackets before sending this to the
            total_ignored_chars = 0
            open_brackets = 0
            offset = None
            tag = None
            temp_text = ""
            # i = 0
            # while i < len(text):
            for i in range(0, len(text)):
                ch = text[i]
                if ch == '[':
                    total_ignored_chars += 1
                    open_brackets += 1
                    if open_brackets == 2:
                        tag = "NE"
                    elif open_brackets == 3:
                        tag = "C"
                    elif open_brackets == 4:
                        tag = "E"
                elif ch == ']':
                    if tag == "NE":
                        # logger.debug(f"annotationsNE1 {textid}: {text[offset:i]}")
                        # logger.debug(f"annotationsNE {textid}: {temp_text[offset-total_ignored_chars:i-total_ignored_chars]}")
                        annotationsNE.append({"charLength": i - offset , "charOffset": offset - total_ignored_chars})
                    elif tag == "C":
                        # logger.debug(f"annotationsC1 {textid}: {text[offset:i]}")
                        # logger.debug(f"annotationsC {textid}: {temp_text[offset-total_ignored_chars:i-total_ignored_chars]}")
                        annotationsC.append({"charLength": i - offset, "charOffset": offset - total_ignored_chars})
                    elif tag == "E":
                        # logger.debug(f"annotationsEither1 {textid}: {text[offset:i]}")
                        # logger.debug(f"annotationsEither {textid}: {temp_text[offset-total_ignored_chars:i-total_ignored_chars]}")
                        annotationsEither.append({"charLength": i - offset, "charOffset": offset - total_ignored_chars})
                    total_ignored_chars += 1
                    open_brackets -= 1
                    offset = None
                    tag = None
                else:
                    temp_text += ch
                    if tag is None:
                        continue
                    if offset is None:
                        offset = i
            text = temp_text
            if len(annotationsC) > 0:
                for mention in annotationsC:
                    logger.debug(f"annotationsC {textid}: {text[mention['charOffset']:mention['charOffset'] + mention['charLength']]}")
            if len(annotationsNE) > 0:
                for mention in annotationsNE:
                    logger.debug(f"annotationsNE {textid}: {text[mention['charOffset']:mention['charOffset'] + mention['charLength']]}")
            if len(annotationsEither) > 0:
                for mention in annotationsEither:
                    logger.debug(f"annotationsEither {textid}: {text[mention['charOffset']:mention['charOffset'] + mention['charLength']]}")

            # We are adding the "either" tags to both named entity and concept annotations
            # in case of joint linking, we will get one final result for them.
            # in case of separate linking, we may get 2 different results for them one NE one C, and we will add both to our results
            for e in annotationsEither:
                annotationsNE.append(e)
                annotationsC.append(e)

        else:
            text = text.replace("[", "")
            text = text.replace("]", "")

        headers = {'accept': 'application/json', 'content-type': 'application/json'}
        data = {"docId": "{}".format(get_file_name(textid, self.get_benchmark_name(), self.get_benchmark_querytype())),
                "text": "{}".format(text),
                "extractConcepts": "{}".format(str(self.cfg["extractConcepts"])),
                "language": "en",
                "pipeline": self.pipeline,
                "annotatedMentionsNE": annotationsNE,
                "annotatedMentionsC": annotationsC
                }

        try:
            r = requests.post(url=self.server, data=json.dumps(data), headers=headers)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(e)

        # logger.debug(f"entitylinking id:{textid} {benchmark_name} {benchmark_querytype}  status:{r.status_code}")
        if r.status_code == 200:
            with open(join(out_dir, get_file_name(textid, self.get_benchmark_name(), self.get_benchmark_querytype())), 'w') as f:
                f.write(json.dumps(r.json(), sort_keys=True, indent=4))

            if 'entities' in r.json():
                for e in r.json()['entities']:
                    self.entity_descriptions[e['name']] = ""
        else:
            raise RuntimeError(f"request status_code is {r.status_code}")

    def load_descriptions(self):
        if self.cfg["descriptions"] == "YAGO_long_short":
            self.load_YAGOdescriptions()
        else:
            raise NotImplementedError("only have YAGO's long and short descriptions implemented")

    def load_YAGOdescriptions(self):
        with open(join(self.yagodescription_dir, 'wikipediaEntityDescriptions_en.tsv'), "r") as f:
            reader = csv.reader(f, delimiter='\t', quotechar='"')
            next(reader)
            for line in reader:
                if len(line) < 2:
                    continue
                entity = line[1].strip().replace("_", " ")
                entity = entity[1:-1]
                if entity not in self.entity_descriptions.keys():
                    continue
                des = line[3].strip()
                self.entity_descriptions[entity] += des + '\n'

        with open(join(self.yagodescription_dir, 'wikidataEntityDescriptions.tsv'), "r") as f:
            reader = csv.reader(f, delimiter='\t', quotechar='"')
            next(reader)
            for line in reader:
                if len(line) < 2:
                    continue
                entity = line[1].strip().replace("_", " ")
                entity = entity[1:-1]
                if entity not in self.entity_descriptions.keys():
                    continue
                des = line[3].strip()
                lang = des[des.find('@') + 1:len(des)]
                des = des[0:des.find('@')]
                if lang == 'en':
                    self.entity_descriptions[entity] += des + '\n'

    def get_entity_description(self, entity):
        return self.entity_descriptions[entity]

    def get_all_entities(self, textid):
        data = json.load(open(join(self.get_extracted_entities_cache_path(), get_file_name(textid, self.get_benchmark_name(), self.get_benchmark_querytype())), 'r'))

        named_entities = set()
        concepts = set()

        if 'entities' in data:
            named_entities.update([e['name'] for e in data['entities'] if e['type'] != 'CONCEPT'])
            concepts.update([e['name'] for e in data['entities'] if e['type'] == 'CONCEPT'])

        return {"NE": list(named_entities), "C": list(concepts)}