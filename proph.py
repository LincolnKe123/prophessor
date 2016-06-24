import sys
import random
from local_settings import *
from automation.group_membership import load as load_group_membership
from automation.group_membership import translate as group_translator
from automation.diffs import diffs as submitted_diffs
from phabricator.project import project as phab_project
from phabricator.user import user as phab_user
from phabricator.diff import diff as phab_diff
from phabricator.policy import policy as phab_policy

arg_task = sys.argv[1]


class LoadRawDiffs():
    def go(self, dir, project_part):
        diff_files = submitted_diffs.get_all(dir)
        for diff_file in diff_files:
            self.create_diff_and_revision(os.path.join(dir, diff_file), project_part)

    def create_diff_and_revision(self, diff_file, project_part):
        group_number = submitted_diffs.get_diff_group_number(diff_file)
        if not group_number:
            print('Error: Could not determine group number from diff filename.')
            return -1
        project_name = group_translator.build_project_name(
            group_num=group_number,
            project_part=project_part,
            is_marking_group=False
        )
        # this code will only run if we know a group to which we should assign this diff to
        diff_id = self.create_diff_from_file(diff_file)
        if diff_id < 0:
            print('Error: Could not create differential with file: %s' % diff_file)
            return -1
        # this code will only run if we successfully created a diff
        revision_id = phab_diff.create_revision(
            diff_id=diff_id,
            title=project_name
        )
        if not revision_id:
            print('Error: Unable to create revision for diff file: %s' % diff_file)
        # this code will only run if we have successfully created a diff & revision
        policy_phid = phab_policy.create_project_policy([project_name])
        if not policy_phid:
            print("Error: unable to create policy")
        # this code will only run if we have a policy to add to our new revision
        phab_diff.set_revision_policy(
            revision_id=revision_id,
            view_policy=policy_phid,
            edit_policy=policy_phid
        )
        print("Success for project: %s" % (project_name))
        print("(diff_id: %s revision_id: %s policy_phid: %s diff_file: %s)" % (
            diff_id,
            revision_id,
            policy_phid,
            diff_file
        ))


    def create_diff_from_file(self, diff_location):
        """
        Create a phabricator diff from a file
        :param diff_location: String: Location of the file
        :return: ID of created diff if successful. -1 if failure
        """
        with open(diff_location, 'r') as file:
            data = file.read()
            return phab_diff.create_raw(diff=data)


class Enroll():
    def go(self, csv):
        """
        go creates users.
        """
        # Create users
        users = load_group_membership.from_csv(csv)
        success = self.create_users(users)
        if success:
            print('User creation completed successfully.')
        else:
            print('User creation failed.')

    def create_users(self, users):
        """
        create_users creates users in Phabricator from a Dict of users.
        :param users: Dictionary of users.
        :return: Boolean True if successful.
        """
        success = True
        for user in users:
            error = phab_user.create(
                user['User Name'],
                user['Password'],
                "%s %s" % (user['First Name'], user['Last Name']),
                user['Email']
            )
            if error:
                success = False
                print("Creating user %s %s %s failed. Attention is required." % (
                    user['User Name'],
                    user['First Name'],
                    user['Last Name']
                ))
            else:
                print("%s (%s %s) successfully created." % (
                    user['User Name'],
                    user['First Name'],
                    user['Last Name']
                ))
        return success


class CreateProjects():
    def go(self, csv, project_part, is_marking_group):
        if is_marking_group:
            self.create_marking_projects(csv, project_part, is_marking_group)
        else:
            self.create_student_projects(csv, project_part, is_marking_group)

    def create_marking_projects(self, students_csv, markers_csv, project_part, icon="policy", color="red"):
        """
        create_project creates projects in Phabricator from a csv.
        :param groups: A unique list of projects.
        :param icon: String of phab icon name.
        :param color: String of phab color.
        :return: None
        """
        all_group_codes = load_group_membership.unique_groups(students_csv)
        all_tutors = load_group_membership.usernames(markers_csv)
        allocations = self.get_random_tutor_marking_allocations(all_tutors, all_group_codes)

        for tutor, group_codes in allocations.iteritems():
            print("Tutor %s is marking groups: %s" % (tutor, group_codes)) # this is in a separate loop to make it print cleanly

        for tutor, group_codes in allocations.iteritems():
            tutor_phid = phab_user.get_phid_from_username(tutor)
            for group_code in group_codes:
                group_name = group_translator.get_project_name_from_group_code(
                    group_code=group_code,
                    project_part=project_part,
                    is_marking_group=True
                )
                phab_project.create(group_name, icon, color, [tutor_phid])
                print("Created group: %s" % (group_name,))

    def get_random_tutor_marking_allocations(self, tutors=[], groups=[]):
        if not tutors:
            raise Exception("Error: No tutor usernames")
        random.shuffle(groups)
        tutor_allocations = {tutor: [] for tutor in tutors}
        unallocated_groups = list(groups)

        tutor_index = 0
        while len(unallocated_groups):
            cur_group = unallocated_groups.pop()
            tutor_allocations[tutors[tutor_index]].append(cur_group)
            tutor_index += 1
            tutor_index %= len(tutors)

        return tutor_allocations

    def create_student_projects(self, csv, project_part, icon="policy", color="red"):
        """
        create_project creates projects in Phabricator from a csv.
        :param groups: A unique list of projects.
        :param icon: String of phab icon name.
        :param color: String of phab color.
        :return: None
        """
        groups = load_group_membership.unique_groups(csv)
        for group_code in groups:
            group_name = group_translator.get_project_name_from_group_code(
                group_code=group_code,
                project_part=project_part,
                is_marking_group=False
            )
            if group_name:
                usernames = load_group_membership.users_for_group(csv, group_code)
                phids = []
                for u in usernames:
                    phids.append(phab_user.get_phid_from_username(u))
                phids = phids + PHAB_SUPER_USER_PHIDS

                phab_project.create(group_name, icon, color, phids)
                print("Created group: %s" % (group_name,))
            else:
                print("Skipped: %s" % (group_code,))


def thanks():
    print("")
    print("Task complete. (  " + u"\uff65\u203f\uff65".encode('utf-8') + " )")

# Parse arguments to do stuff

if arg_task == 'enroll':
    # python proph.py enroll group_members.csv
    action = Enroll()
    action.go(sys.argv[2])
    thanks()

elif arg_task == 'create-student-groups':
    # python proph.py create-student-groups students.csv 1234
    part = int(sys.argv[3])
    action = CreateProjects()
    action.create_student_projects(sys.argv[2], part)
    thanks()

elif arg_task == 'create-marker-groups':
    # python proph.py create-marker-groups students.csv markers.csv 1234
    part = int(sys.argv[4])
    action = CreateProjects()
    action.create_marking_projects(sys.argv[2], sys.argv[3], part, True)
    thanks()

elif arg_task == 'load-diffs':
    # python proph.py load-diffs diffs/ 1234
    part = int(sys.argv[3])
    action = LoadRawDiffs()
    action.go(sys.argv[2], part)
    thanks()

else:
    print("Unknown command. " + u"\u00af\_(\u30c4)_/\u00af".encode('utf-8'))


