from django.db import models
from django.db.models import Q
from .raw_models import *

class RadUserManager(models.Manager):
    def get_query_set(self):
        return super(RadUserManager, self).get_query_set().filter(attribute='User-Password', op=':=')
            
    def create(self, **kwargs):
        if 'password' in kwargs:
            kwargs['value'] = kwargs['password']
            del kwargs['password']
        kwargs.update(dict(attribute='User-Password', op=':='))
        return super(RadUserManager, self).create(**kwargs)

    def get_or_create(self, **kwargs):
        if 'defaults' not in kwargs:
            kwargs['defaults'] = {}
        #query by password is not useful
        #if 'password' in kwargs:
        #    kwargs['value'] = kwargs['password']
        #    del kwargs['password']
        kwargs['defaults'].update(dict(attribute='User-Password', op=':='))
        if 'password' in kwargs['defaults']:
            kwargs['defaults']['value'] = kwargs['defaults']['password']
            del kwargs['defaults']['password']
        return super(RadUserManager, self).get_or_create(**kwargs)
 
    def count_info(self):
        total_count = self.values('username').distinct().count()
        suspended_count = (Radcheck.objects
            .filter(attribute='Auth-Type', op=':=', value='Reject')
            .values('username')
            .distinct().count())
    
        return {
            'total' : total_count,
            'suspended' : suspended_count,
            'active' : total_count - suspended_count
        }

    def get_suspended_users(self):
        suspended_users = (Radcheck.objects
            .filter(username__in=usernames, attribute='Auth-Type', op=':=', value='Reject')
            .values_list('username', flat=True)
            .distinct())
        return suspended_users
        
    def query_active_user(self):
        return self.extra(where=['''
            NOT EXISTS(
                SELECT 1 FROM radcheck as rc 
                WHERE rc.username = radcheck.username
                  AND attribute='Auth-Type'
                  AND op=':='
                  AND value='Reject'
            )
            '''])

    def query_suspended_user(self):
        return self.extra(where=['''
            EXISTS(
                SELECT 1 FROM radcheck as rc 
                WHERE rc.username = radcheck.username
                  AND attribute='Auth-Type'
                  AND op=':='
                  AND value='Reject'
            )
            '''])

class RadUser(Radcheck):
    objects = RadUserManager()

    class Meta:
        proxy = True

    @property
    def password(self):
        return self.value

    @property
    def is_suspended(self):
        return Radcheck.objects.filter(
            username=self.username,
            attribute='Auth-Type',
            op=':=',
            value='Reject').exists()
    
    @property
    def groups(self):
        return (Radusergroup.objects
            .filter(username=self.username)
            .order_by('priority')
            .values_list('groupname', flat=True)
            )
        
    def change_password(self, password):
        self.value = password
        self.save()

    def toggle_suspended(self, is_suspended):
        username = self.username
        if is_suspended:
            Radcheck.objects.get_or_create(username=username, attribute='Auth-Type', op=':=', value='Reject')
        else:
            Radcheck.objects.filter(username=username, attribute='Auth-Type', op=':=', value='Reject').delete()
    
    def change_groups(self, groups):
        username = self.username
        old_groups = self.groups
        if set(old_groups) != set(groups):
            to_delete = set(old_groups) - set(groups)
            Radusergroup.objects.filter(username=username, groupname__in=to_delete).delete()

            to_add = set(groups) - set(old_groups)
            for group in to_add:
                Radusergroup.objects.create(username=username, groupname=group)

    def update(self, password=None, is_suspended=None, groups=None):
        #update password 
        record = self
        if password is not None and record.value != password:
            self.change_password(password)

        #update valid state
        if is_suspended is not None:
            self.toggle_suspended(is_suspended)
            
        #update groups 
        if groups is not None and type(groups) in (list, tuple):
            self.change_groups(groups)


def get_radgroup_count():
    groups = list(Radusergroup.objects.values_list('groupname', flat=True).distinct())
    groups += list(Radgroupcheck.objects.values_list('groupname', flat=True).distinct())

    return len(set(groups))

def get_groups():
    groups = list(Radusergroup.objects.values_list('groupname', flat=True).distinct())
    groups += list(Radgroupcheck.objects.values_list('groupname', flat=True).distinct())
    groups = set(groups)
    return [RadGroup(groupname) for groupname in groups]


def get_group(groupname):
    gs = Radgroupcheck.objects.filter(groupname=groupname)
    if gs.count() > 0:
        return RadGroup(groupname)
    gs = Radusergroup.objects.filter(groupname=groupname)
    if gs.count() > 0:
        return RadGroup(groupname)
   
class RadGroup(object):

    def __init__(self, groupname):
        self.groupname = groupname

    @property
    def simultaneous_use(self):
        try:
            return Radgroupcheck.objects.get(groupname=self.groupname,
                attribute='Simultaneous-Use', op=':=').value
        except Radgroupcheck.DoesNotExist:
            return None
            
    def set_simultaneous_use(self, su):
        radg, created = Radgroupcheck.objects.get_or_create(
            groupname=self.groupname,
            attribute='Simultaneous-Use', op=':=',
            defaults={'value' : su})

        if not created:
            radg.value = su
            radg.save()

    @property
    def user_count(self):
        return Radusergroup.objects.filter(groupname=self.groupname).values('username').distinct().count()
