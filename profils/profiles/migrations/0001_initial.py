
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Language',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(help_text='code ISO 639-1, par exemple fr', max_length=8, unique=True)),
                ('name', models.CharField(max_length=80)),
            ],
            options={
                'ordering': ('name',),
            },
        ),
        migrations.CreateModel(
            name='ProfessionalProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('headline', models.CharField(blank=True, default='', help_text="titre professionnel, par exemple 'Developpeur backend Java'", max_length=160)),
                ('summary', models.TextField(blank=True, default='')),
                ('photo_url', models.CharField(blank=True, default='', max_length=1024)),
                ('cover_url', models.CharField(blank=True, default='', max_length=1024)),
                ('location_city', models.CharField(blank=True, default='', max_length=120)),
                ('location_region', models.CharField(blank=True, default='', max_length=120)),
                ('location_country', models.CharField(blank=True, default='', help_text='code pays ISO 3166-1 alpha-2, par exemple FR', max_length=2)),
                ('professional_field', models.CharField(blank=True, choices=[('SOFTWARE', 'Developpement logiciel'), ('DATA', 'Donnees et IA'), ('INFRASTRUCTURE', 'Infrastructure et systemes'), ('SECURITY', 'Cybersecurite'), ('DESIGN', 'Design'), ('PRODUCT', 'Produit et gestion de projet'), ('MARKETING', 'Marketing et communication'), ('SALES', 'Commerce et vente'), ('FINANCE', 'Finance et comptabilite'), ('HR', 'Ressources humaines'), ('LEGAL', 'Juridique'), ('HEALTH', 'Sante'), ('EDUCATION', 'Enseignement et formation'), ('INDUSTRY', 'Industrie et ingenierie'), ('LOGISTICS', 'Transport et logistique'), ('HOSPITALITY', 'Hotellerie et restauration'), ('OTHER', 'Autre')], default='', max_length=24)),
                ('availability_status', models.CharField(choices=[('OPEN_TO_WORK', 'En recherche active'), ('OPEN_TO_OPPORTUNITIES', 'Ouvert aux opportunites'), ('CURRENTLY_EMPLOYED', 'En poste'), ('NOT_LOOKING', 'Pas en recherche')], default='NOT_LOOKING', max_length=24)),
                ('available_from', models.DateField(blank=True, null=True)),
                ('open_to_remote', models.BooleanField(default=False)),
                ('open_to_hybrid', models.BooleanField(default=False)),
                ('open_to_onsite', models.BooleanField(default=False)),
                ('willing_to_relocate', models.BooleanField(default=False)),
                ('mobility_radius_km', models.PositiveIntegerField(blank=True, null=True)),
                ('mobility_note', models.CharField(blank=True, default='', max_length=240)),
                ('visibility', models.CharField(choices=[('PUBLIC', 'Public'), ('REGISTERED_USERS', 'Utilisateurs inscrits'), ('PRIVATE', 'Prive')], default='REGISTERED_USERS', max_length=20)),
                ('total_experience_months', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='professional_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-updated_at',),
                'permissions': (('manage_skill_catalog', 'Peut gerer le referentiel de competences'), ('view_private_profile', 'Peut consulter un profil prive'), ('moderate_profile', 'Peut moderer un profil')),
            },
        ),
        migrations.CreateModel(
            name='Education',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_date', models.DateField()),
                ('end_date', models.DateField(blank=True, null=True)),
                ('is_current', models.BooleanField(default=False)),
                ('order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('institution', models.CharField(max_length=160)),
                ('degree', models.CharField(blank=True, default='', max_length=160)),
                ('degree_level', models.CharField(blank=True, choices=[('NONE', 'Sans diplome'), ('SECONDARY', 'CAP, BEP'), ('BAC', 'Baccalaureat'), ('BAC_2', 'Bac +2'), ('BAC_3', 'Bac +3 (licence)'), ('BAC_5', 'Bac +5 (master, ingenieur)'), ('BAC_8', 'Bac +8 (doctorat)')], default='', max_length=20)),
                ('field_of_study', models.CharField(blank=True, default='', max_length=160)),
                ('description', models.TextField(blank=True, default='')),
                ('diploma_url', models.URLField(blank=True, default='', max_length=1024)),
                ('diploma_verified', models.BooleanField(default=False)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='education', to='profiles.professionalprofile')),
            ],
            options={
                'verbose_name_plural': 'education',
                'ordering': ('-is_current', '-start_date', 'order'),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Certification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=160)),
                ('issuer', models.CharField(blank=True, default='', max_length=160)),
                ('issued_on', models.DateField(blank=True, null=True)),
                ('expires_on', models.DateField(blank=True, null=True)),
                ('credential_id', models.CharField(blank=True, default='', max_length=160)),
                ('verification_url', models.URLField(blank=True, default='', max_length=1024)),
                ('order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='certifications', to='profiles.professionalprofile')),
            ],
            options={
                'ordering': ('-issued_on', 'order', 'id'),
            },
        ),
        migrations.CreateModel(
            name='ProfileContractType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contract_type', models.CharField(choices=[('CDI', 'CDI'), ('CDD', 'CDD'), ('INTERNSHIP', 'Stage'), ('APPRENTICESHIP', 'Alternance'), ('FREELANCE', 'Freelance'), ('PART_TIME', 'Temps partiel'), ('TEMPORARY', 'Interim'), ('VOLUNTEER', 'Benevolat')], max_length=20)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contract_types', to='profiles.professionalprofile')),
            ],
            options={
                'ordering': ('contract_type',),
            },
        ),
        migrations.CreateModel(
            name='ProfileLink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('PORTFOLIO', 'Portfolio'), ('WEBSITE', 'Site web'), ('GITHUB', 'GitHub'), ('GITLAB', 'GitLab'), ('LINKEDIN', 'LinkedIn'), ('BEHANCE', 'Behance'), ('DRIBBBLE', 'Dribbble'), ('OTHER', 'Autre')], default='OTHER', max_length=20)),
                ('label', models.CharField(blank=True, default='', max_length=120)),
                ('url', models.URLField(max_length=1024)),
                ('order', models.PositiveIntegerField(default=0)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='links', to='profiles.professionalprofile')),
            ],
            options={
                'ordering': ('order', 'id'),
            },
        ),
        migrations.CreateModel(
            name='ProfileSearchSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('searchable', models.BooleanField(default=True, help_text='apparaitre dans les resultats de recherche')),
                ('appear_in_video_feed', models.BooleanField(default=True, help_text='reserve au futur feed video (section 18)')),
                ('show_availability_in_results', models.BooleanField(default=True)),
                ('contactable_by_recruiters', models.BooleanField(default=True)),
                ('profile', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='search_config', to='profiles.professionalprofile')),
            ],
        ),
        migrations.CreateModel(
            name='ProfileVideo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=160)),
                ('description', models.TextField(blank=True, default='')),
                ('file_url', models.CharField(blank=True, default='', max_length=1024)),
                ('thumbnail_url', models.CharField(blank=True, default='', max_length=1024)),
                ('duration_seconds', models.PositiveIntegerField(blank=True, null=True)),
                ('status', models.CharField(choices=[('DRAFT', 'Brouillon'), ('PROCESSING', 'En traitement'), ('PUBLISHED', 'Publiee'), ('HIDDEN', 'Masquee'), ('DELETED', 'Supprimee')], default='DRAFT', max_length=16)),
                ('visibility', models.CharField(choices=[('PUBLIC', 'Public'), ('REGISTERED_USERS', 'Utilisateurs inscrits'), ('PRIVATE', 'Prive')], default='PUBLIC', max_length=20)),
                ('tags', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('view_count', models.PositiveIntegerField(default=0)),
                ('like_count', models.PositiveIntegerField(default=0)),
                ('share_count', models.PositiveIntegerField(default=0)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='videos', to='profiles.professionalprofile')),
            ],
            options={
                'ordering': ('-published_at', '-created_at'),
            },
        ),
        migrations.CreateModel(
            name='ProfileVisibility',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('skills_visibility', models.CharField(choices=[('PUBLIC', 'Public'), ('REGISTERED_USERS', 'Utilisateurs inscrits'), ('PRIVATE', 'Prive')], default='PUBLIC', max_length=20)),
                ('experiences_visibility', models.CharField(choices=[('PUBLIC', 'Public'), ('REGISTERED_USERS', 'Utilisateurs inscrits'), ('PRIVATE', 'Prive')], default='PUBLIC', max_length=20)),
                ('education_visibility', models.CharField(choices=[('PUBLIC', 'Public'), ('REGISTERED_USERS', 'Utilisateurs inscrits'), ('PRIVATE', 'Prive')], default='PUBLIC', max_length=20)),
                ('certifications_visibility', models.CharField(choices=[('PUBLIC', 'Public'), ('REGISTERED_USERS', 'Utilisateurs inscrits'), ('PRIVATE', 'Prive')], default='PUBLIC', max_length=20)),
                ('languages_visibility', models.CharField(choices=[('PUBLIC', 'Public'), ('REGISTERED_USERS', 'Utilisateurs inscrits'), ('PRIVATE', 'Prive')], default='PUBLIC', max_length=20)),
                ('projects_visibility', models.CharField(choices=[('PUBLIC', 'Public'), ('REGISTERED_USERS', 'Utilisateurs inscrits'), ('PRIVATE', 'Prive')], default='PUBLIC', max_length=20)),
                ('availability_visibility', models.CharField(choices=[('PUBLIC', 'Public'), ('REGISTERED_USERS', 'Utilisateurs inscrits'), ('PRIVATE', 'Prive')], default='REGISTERED_USERS', max_length=20)),
                ('videos_visibility', models.CharField(choices=[('PUBLIC', 'Public'), ('REGISTERED_USERS', 'Utilisateurs inscrits'), ('PRIVATE', 'Prive')], default='PUBLIC', max_length=20)),
                ('links_visibility', models.CharField(choices=[('PUBLIC', 'Public'), ('REGISTERED_USERS', 'Utilisateurs inscrits'), ('PRIVATE', 'Prive')], default='PUBLIC', max_length=20)),
                ('profile', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='visibility_config', to='profiles.professionalprofile')),
            ],
        ),
        migrations.CreateModel(
            name='Project',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=160)),
                ('description', models.TextField(blank=True, default='')),
                ('role', models.CharField(blank=True, default='', max_length=160)),
                ('url', models.URLField(blank=True, default='', max_length=1024)),
                ('started_on', models.DateField(blank=True, null=True)),
                ('ended_on', models.DateField(blank=True, null=True)),
                ('order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='projects', to='profiles.professionalprofile')),
                ('video', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='projects', to='profiles.profilevideo')),
            ],
            options={
                'ordering': ('order', '-started_on', 'id'),
            },
        ),
        migrations.CreateModel(
            name='Skill',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=80, unique=True)),
                ('name', models.CharField(max_length=80)),
                ('category', models.CharField(choices=[('LANGUAGE', 'Langage'), ('FRAMEWORK', 'Framework'), ('TOOL', 'Outil'), ('DATABASE', 'Base de donnees'), ('CLOUD', 'Cloud et infrastructure'), ('METHOD', 'Methode'), ('SOFT', 'Savoir-etre'), ('OTHER', 'Autre')], default='OTHER', max_length=20)),
                ('description', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ('name',),
                'indexes': [models.Index(fields=['category'], name='profiles_sk_categor_fcdf63_idx'), models.Index(fields=['name'], name='profiles_sk_name_1f6740_idx')],
            },
        ),
        migrations.CreateModel(
            name='ProjectSkill',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0)),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='skill_links', to='profiles.project')),
                ('skill', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='profiles.skill')),
            ],
            options={
                'ordering': ('order', 'id'),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ProfileVideoSkill',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0)),
                ('video', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='skill_links', to='profiles.profilevideo')),
                ('skill', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='profiles.skill')),
            ],
            options={
                'ordering': ('order', 'id'),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='EducationSkill',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0)),
                ('education', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='skill_links', to='profiles.education')),
                ('skill', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='profiles.skill')),
            ],
            options={
                'ordering': ('order', 'id'),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='CertificationSkill',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0)),
                ('certification', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='skill_links', to='profiles.certification')),
                ('skill', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='profiles.skill')),
            ],
            options={
                'ordering': ('order', 'id'),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='SkillAlias',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('normalized', models.SlugField(max_length=80, unique=True)),
                ('label', models.CharField(blank=True, default='', max_length=80)),
                ('skill', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='aliases', to='profiles.skill')),
            ],
            options={
                'ordering': ('normalized',),
            },
        ),
        migrations.CreateModel(
            name='UserLanguage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('level', models.CharField(choices=[('A1', 'A1 - decouverte'), ('A2', 'A2 - survie'), ('B1', 'B1 - seuil'), ('B2', 'B2 - avance'), ('C1', 'C1 - autonome'), ('C2', 'C2 - maitrise'), ('NATIVE', 'Langue maternelle')], default='B1', max_length=12)),
                ('level_rank', models.PositiveSmallIntegerField(default=0, editable=False)),
                ('order', models.PositiveIntegerField(default=0)),
                ('language', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='speakers', to='profiles.language')),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='languages', to='profiles.professionalprofile')),
            ],
            options={
                'ordering': ('order', '-level_rank', 'language__name'),
            },
        ),
        migrations.CreateModel(
            name='UserSkill',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('level', models.CharField(choices=[('BEGINNER', 'Debutant'), ('INTERMEDIATE', 'Intermediaire'), ('ADVANCED', 'Avance'), ('EXPERT', 'Expert')], default='BEGINNER', max_length=24)),
                ('level_rank', models.PositiveSmallIntegerField(default=0, editable=False)),
                ('years_experience', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('order', models.PositiveIntegerField(default=0)),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('evidence_url', models.URLField(blank=True, default='', max_length=1024)),
                ('evidence_certification', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='proven_skills', to='profiles.certification')),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='skills', to='profiles.professionalprofile')),
                ('skill', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='holders', to='profiles.skill')),
            ],
            options={
                'ordering': ('order', '-level_rank', 'skill__name'),
            },
        ),
        migrations.CreateModel(
            name='WorkExperience',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_date', models.DateField()),
                ('end_date', models.DateField(blank=True, null=True)),
                ('is_current', models.BooleanField(default=False)),
                ('order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=160)),
                ('company', models.CharField(max_length=160)),
                ('description', models.TextField(blank=True, default='')),
                ('location_city', models.CharField(blank=True, default='', max_length=120)),
                ('location_country', models.CharField(blank=True, default='', max_length=2)),
                ('contract_type', models.CharField(blank=True, choices=[('CDI', 'CDI'), ('CDD', 'CDD'), ('INTERNSHIP', 'Stage'), ('APPRENTICESHIP', 'Alternance'), ('FREELANCE', 'Freelance'), ('PART_TIME', 'Temps partiel'), ('TEMPORARY', 'Interim'), ('VOLUNTEER', 'Benevolat')], default='', max_length=20)),
                ('profile', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='experiences', to='profiles.professionalprofile')),
            ],
            options={
                'ordering': ('-is_current', '-start_date', 'order'),
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='WorkExperienceSkill',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0)),
                ('experience', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='skill_links', to='profiles.workexperience')),
                ('skill', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='profiles.skill')),
            ],
            options={
                'ordering': ('order', 'id'),
                'abstract': False,
            },
        ),
        migrations.AddIndex(
            model_name='professionalprofile',
            index=models.Index(fields=['visibility', 'availability_status'], name='profiles_pr_visibil_ef28ed_idx'),
        ),
        migrations.AddIndex(
            model_name='professionalprofile',
            index=models.Index(fields=['professional_field'], name='profiles_pr_profess_8f2ab7_idx'),
        ),
        migrations.AddIndex(
            model_name='professionalprofile',
            index=models.Index(fields=['location_country', 'location_city'], name='profiles_pr_locatio_906732_idx'),
        ),
        migrations.AddIndex(
            model_name='professionalprofile',
            index=models.Index(fields=['total_experience_months'], name='profiles_pr_total_e_e7bc73_idx'),
        ),
        migrations.AddIndex(
            model_name='professionalprofile',
            index=models.Index(fields=['updated_at'], name='profiles_pr_updated_429d10_idx'),
        ),
        migrations.AddIndex(
            model_name='education',
            index=models.Index(fields=['profile', '-start_date'], name='profiles_ed_profile_a2db69_idx'),
        ),
        migrations.AddIndex(
            model_name='education',
            index=models.Index(fields=['degree_level'], name='profiles_ed_degree__29c83a_idx'),
        ),
        migrations.AddIndex(
            model_name='education',
            index=models.Index(fields=['institution'], name='profiles_ed_institu_0b2080_idx'),
        ),
        migrations.AddIndex(
            model_name='certification',
            index=models.Index(fields=['profile', '-issued_on'], name='profiles_ce_profile_1d0451_idx'),
        ),
        migrations.AddIndex(
            model_name='certification',
            index=models.Index(fields=['issuer'], name='profiles_ce_issuer_61ed25_idx'),
        ),
        migrations.AddIndex(
            model_name='profilecontracttype',
            index=models.Index(fields=['contract_type'], name='profiles_pr_contrac_7be43a_idx'),
        ),
        migrations.AddConstraint(
            model_name='profilecontracttype',
            constraint=models.UniqueConstraint(fields=('profile', 'contract_type'), name='unique_contract_per_profile'),
        ),
        migrations.AddIndex(
            model_name='profilelink',
            index=models.Index(fields=['profile', 'order'], name='profiles_pr_profile_59479c_idx'),
        ),
        migrations.AddIndex(
            model_name='profilesearchsettings',
            index=models.Index(fields=['searchable'], name='profiles_pr_searcha_365d79_idx'),
        ),
        migrations.AddIndex(
            model_name='profilevideo',
            index=models.Index(fields=['profile', 'status'], name='profiles_pr_profile_3ea95f_idx'),
        ),
        migrations.AddIndex(
            model_name='profilevideo',
            index=models.Index(fields=['status', '-published_at'], name='profiles_pr_status_124658_idx'),
        ),
        migrations.AddIndex(
            model_name='profilevideo',
            index=models.Index(fields=['visibility'], name='profiles_pr_visibil_5bb881_idx'),
        ),
        migrations.AddIndex(
            model_name='project',
            index=models.Index(fields=['profile', 'order'], name='profiles_pr_profile_2bc82c_idx'),
        ),
        migrations.AddIndex(
            model_name='projectskill',
            index=models.Index(fields=['skill'], name='profiles_pr_skill_i_ebc0cd_idx'),
        ),
        migrations.AddConstraint(
            model_name='projectskill',
            constraint=models.UniqueConstraint(fields=('project', 'skill'), name='unique_skill_per_project'),
        ),
        migrations.AddIndex(
            model_name='profilevideoskill',
            index=models.Index(fields=['skill'], name='profiles_pr_skill_i_0b6b63_idx'),
        ),
        migrations.AddConstraint(
            model_name='profilevideoskill',
            constraint=models.UniqueConstraint(fields=('video', 'skill'), name='unique_skill_per_video'),
        ),
        migrations.AddIndex(
            model_name='educationskill',
            index=models.Index(fields=['skill'], name='profiles_ed_skill_i_f5fa09_idx'),
        ),
        migrations.AddConstraint(
            model_name='educationskill',
            constraint=models.UniqueConstraint(fields=('education', 'skill'), name='unique_skill_per_education'),
        ),
        migrations.AddIndex(
            model_name='certificationskill',
            index=models.Index(fields=['skill'], name='profiles_ce_skill_i_7fd83a_idx'),
        ),
        migrations.AddConstraint(
            model_name='certificationskill',
            constraint=models.UniqueConstraint(fields=('certification', 'skill'), name='unique_skill_per_certification'),
        ),
        migrations.AddIndex(
            model_name='userlanguage',
            index=models.Index(fields=['language', 'level_rank'], name='profiles_us_languag_f48879_idx'),
        ),
        migrations.AddIndex(
            model_name='userlanguage',
            index=models.Index(fields=['profile', 'order'], name='profiles_us_profile_e3f8f9_idx'),
        ),
        migrations.AddConstraint(
            model_name='userlanguage',
            constraint=models.UniqueConstraint(fields=('profile', 'language'), name='unique_language_per_profile'),
        ),
        migrations.AddIndex(
            model_name='userskill',
            index=models.Index(fields=['skill', 'level_rank'], name='profiles_us_skill_i_bf274c_idx'),
        ),
        migrations.AddIndex(
            model_name='userskill',
            index=models.Index(fields=['skill', 'years_experience'], name='profiles_us_skill_i_c60bc5_idx'),
        ),
        migrations.AddIndex(
            model_name='userskill',
            index=models.Index(fields=['profile', 'order'], name='profiles_us_profile_57d3fa_idx'),
        ),
        migrations.AddConstraint(
            model_name='userskill',
            constraint=models.UniqueConstraint(fields=('profile', 'skill'), name='unique_skill_per_profile'),
        ),
        migrations.AddIndex(
            model_name='workexperience',
            index=models.Index(fields=['profile', '-start_date'], name='profiles_wo_profile_7c5813_idx'),
        ),
        migrations.AddIndex(
            model_name='workexperience',
            index=models.Index(fields=['company'], name='profiles_wo_company_ee38a1_idx'),
        ),
        migrations.AddIndex(
            model_name='workexperienceskill',
            index=models.Index(fields=['skill'], name='profiles_wo_skill_i_d5de96_idx'),
        ),
        migrations.AddConstraint(
            model_name='workexperienceskill',
            constraint=models.UniqueConstraint(fields=('experience', 'skill'), name='unique_skill_per_experience'),
        ),
    ]
