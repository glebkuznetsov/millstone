"""
Tests for import_util.py.
"""

import os

from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile
from django.test import TestCase

from main.models import Dataset
from main.models import ExperimentSample
from main.models import Project
from main.models import ReferenceGenome
from main.models import Variant
from main.models import VariantSet
from scripts.dynamic_snp_filter_key_map import initialize_filter_key_map
from scripts.import_util import DataImportError
from scripts.import_util import import_reference_genome_from_local_file
from scripts.import_util import import_samples_from_targets_file
from scripts.import_util import import_variant_set_from_vcf
from settings import PWD as GD_ROOT_PATH


TEST_USERNAME = 'gmcdev'
TEST_PASSWORD = 'g3n3d3z'
TEST_EMAIL = 'gmcdev@genomedesigner.freelogy.org'


class TestImportReferenceGenome(TestCase):
    """Tests importing a ReferenceGenome.
    """

    def setUp(self):
        # Test models.
        user = User.objects.create_user(TEST_USERNAME, password=TEST_PASSWORD,
                email=TEST_EMAIL)
        self.project = Project.objects.create(owner=user.get_profile(),
                title='Test Project')


    def test_import_reference_genome_from_local_file(self):
        """Tests importing reference genome.
        """
        TEST_GENBANK_FILE = os.path.join(GD_ROOT_PATH,
                'test_data', 'import_util_test_data', 'mini_mg1655.genbank')

        import_reference_genome_from_local_file(self.project, 'a label',
                TEST_GENBANK_FILE, 'genbank')


    def test_import_reference_genome_from_local_file__fail_if_no_seq(self):
        """Should fail if no sequence in file.
        """
        TEST_GENBANK_FILE__NO_SEQ = os.path.join(GD_ROOT_PATH,
                'test_data', 'import_util_test_data', 'mg1655_no_seq.genbank')

        with self.assertRaises(DataImportError):
            import_reference_genome_from_local_file(self.project, 'a label',
                    TEST_GENBANK_FILE__NO_SEQ, 'genbank')


class TestImportSamplesFromTargetsFile(TestCase):
    """Tests for scripts.import_util.import_samples_from_targets_file().
    """

    def setUp(self):
        # Test models.
        user = User.objects.create_user(TEST_USERNAME, password=TEST_PASSWORD,
                email=TEST_EMAIL)
        test_project = Project.objects.create(owner=user.get_profile(),
                title='Test Project')

    def test_import_samples(self):
        """Tests importing samples from a template file.
        """
        TARGETS_TEMPLATE_FILEPATH = os.path.join(GD_ROOT_PATH, 'main',
                'templates', 'sample_list_targets_template.tsv')

        NUM_SAMPLES_IN_TEMPLATE = 10

        # Grab any project from the database.
        project = Project.objects.all()[0]

        num_experiment_samples_before = len(ExperimentSample.objects.all())
        num_datasets_before = len(Dataset.objects.all())

        # Perform the import.
        with open(TARGETS_TEMPLATE_FILEPATH) as targets_file_fh:
            import_samples_from_targets_file(project,
                    UploadedFile(targets_file_fh))

        num_experiment_samples_after = len(ExperimentSample.objects.all())
        num_datasets_after = len(Dataset.objects.all())

        # Make sure the right amount of models were added.
        self.assertEqual(NUM_SAMPLES_IN_TEMPLATE,
                num_experiment_samples_after - num_experiment_samples_before)
        self.assertEqual(2 * NUM_SAMPLES_IN_TEMPLATE,
                num_datasets_after - num_datasets_before)

        # TODO: Check the filepaths as well.

class TestImportVariantSetFromVCFFile(TestCase):
    """Tests for scripts.import_util.import_samples_from_targets_file().
    """

    def setUp(self):
        # Test models.
        user = User.objects.create_user(TEST_USERNAME, password=TEST_PASSWORD,
                email=TEST_EMAIL)
        test_project = Project.objects.create(owner=user.get_profile(),
                title='Test Project')
        self.ref_genome = ReferenceGenome.objects.create(project=test_project,
                label='refgenome', num_chromosomes=1, num_bases=1000)

        initialize_filter_key_map(self.ref_genome)



    def test_import_variant_set(self):
        """Tests importing variant sets from a pared-down vcf file
        containing only chromosome, position info, etc.
        """

        VARIANT_SET_VCF_FILEPATH = os.path.join(GD_ROOT_PATH,
                'test_data', 'fake_genome_and_reads',
                'test_genome_variant_set.vcf')

        NUM_VARIANTS_IN_SET = 20

        VARIANT_SET_NAME = 'Test Set'

        import_variant_set_from_vcf(
                self.ref_genome, VARIANT_SET_NAME,
                VARIANT_SET_VCF_FILEPATH)

        new_variant_set = VariantSet.objects.get(
                reference_genome=self.ref_genome,
                label=VARIANT_SET_NAME)

        self.assertEqual(NUM_VARIANTS_IN_SET,
                len(new_variant_set.variants.all()))

        # Spot-check a few variants.
        v_1128 = Variant.objects.get(reference_genome=self.ref_genome,
                position=1128)
        self.assertEqual(['C'], v_1128.get_alternates())

        v_553 = Variant.objects.get(reference_genome=self.ref_genome,
                position=553)
        self.assertEqual(['C','G'], v_553.get_alternates())
