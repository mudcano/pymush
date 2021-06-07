from mudstring.patches.text import MudText

from pymush.engine.cmdqueue import BreakQueueException, QueueEntryType
from pymush.utils.text import case_match, truthy

from .base import Command, MushCommand, CommandException, PythonCommandMatcher


class _ScriptCommand(MushCommand):
    help_category = 'Building'


class DoListCommand(_ScriptCommand):
    name = '@dolist'
    aliases = ['@dol', '@doli', '@dolis']
    available_switches = ['delimit', 'clearregs', 'inline', 'inplace', 'localize', 'nobreak', 'notify']

    def execute(self):
        lsargs, rsargs = self.eqsplit_args(self.args)
        if 'inplace' in self.switches:
            self.switches.update({"inline", "nobreak", "localize"})

        lsargs = self.parser.evaluate(lsargs)

        if 'delimit' in self.switches:
            delim, _ = lsargs.plain.split(' ', 1)
            if not len(delim) == 1:
                raise CommandException("Delimiter must be one character.")
            elements = lsargs[2:]
        else:
            delim = ' '
            elements = lsargs

        if not len(elements):
            return

        elements = self.split_by(elements, delim)
        nobreak = 'nobreak' in self.switches

        if 'inline' in self.switches:
            for i, elem in enumerate(elements):
                self.entry.execute_action_list(rsargs, nobreak=nobreak, dnum=i, dvar=elem)
        else:
            for i, elem in enumerate(elements):
                self.entry.spawn_action_list(rsargs, dnum=i, dvar=elem)


class AssertCommand(_ScriptCommand):
    name = '@assert'
    aliases = ['@as', '@ass', '@asse', '@asser']
    available_switches = ['queued']

    def execute(self):
        lsargs, rsargs = self.eqsplit_args(self.args)
        if not self.parser.truthy(self.parser.evaluate(lsargs)):
            if rsargs:
                if 'queued' in self.switches:
                    self.entry.spawn_action_list(rsargs)
                else:
                    self.entry.execute_action_list(rsargs)
            raise BreakQueueException(self)


class BreakCommand(_ScriptCommand):
    name = '@break'
    aliases = ['@br', '@bre', '@brea']
    available_switches = ['queued']

    def execute(self):
        lsargs, rsargs = self.eqsplit_args(self.args)
        if self.parser.truthy(self.parser.evaluate(lsargs)):
            if rsargs:
                if 'queued' in self.switches:
                    self.entry.spawn_action_list(rsargs)
                else:
                    self.entry.execute_action_list(rsargs)
            raise BreakQueueException(self)


class TriggerCommand(_ScriptCommand):
    name = '@trigger'
    aliases = ['@tr', '@tri', '@trig', '@trigg', '@trigge']


class IncludeCommand(_ScriptCommand):
    name = '@include'
    aliases = ['@inc', '@incl', '@inclu', '@includ']
    available_switches = ['nobreak']

    def execute(self):
        lsargs, rsargs = self.eqsplit_args(self.args)
        obj, attr_name, err = self.target_obj_attr(self.parser.evaluate(lsargs),
                                                   default=self.executor)
        if err:
            self.executor.msg(MudText(err))

        actions = self.get_attr(obj, attr_name=attr_name)

        if not truthy(actions):
            self.executor.msg(f"{self.name} cannot use that attribute. Is it accessible, and an action list?")

        number_args = [self.parser.evaluate(arg) for arg in self.split_args(rsargs)]
        inter = self.interpreter.make_child(actions, split=True)
        inter.execute(number_args=number_args, nobreak='nobreak' in self.switches)


class SwitchCommand(_ScriptCommand):
    name = '@switch'
    aliases = ['@swi', '@swit', '@switc']
    available_switches = ['queued', 'all']

    def execute(self):
        lsargs, rsargs = self.eqsplit_args(self.args)
        matcher = self.parser.evaluate(lsargs)
        s_rsargs = self.split_args(rsargs)

        actions = list()
        default = None
        if len(s_rsargs) % 2 == 0:
            args = s_rsargs[1:]
        else:
            default = s_rsargs[-1]
            args = s_rsargs[1:-1]

        stop_first = 'all' not in self.switches

        for case, outcome in zip(args[0::2], args[1::2]):
            if case_match(matcher, self.parser.evaluate(case, stext=matcher)):
                actions.append(outcome)
                if stop_first:
                    break

        if not actions:
            if default:
                actions.append(default)

        if actions:
            if 'queued' in self.switches:
                for action in actions:
                    self.interpreter.spawn_action_list(self.parser.make_child_frame(stext=matcher), action)
            else:
                inter = self.interpreter
                for action in actions:
                    inter = inter.make_child(action, split=True)
                    inter.execute(stext=matcher)


class SetCommand(_ScriptCommand):
    name = '@set'
    aliases = ['@se']

    def execute(self):
        lsargs, rsargs = self.eqsplit_args(self.args)

        obj, err = self.executor.locate_object(name=self.parser.evaluate(lsargs), first_only=True)
        if err:
            self.executor.msg(err)
            return
        obj = obj[0]
        to_set = self.parser.evaluate(rsargs)

        idx = to_set.find(':')
        if idx == -1:
            self.executor.msg("Malformed @set syntax")
        attr_name = to_set[:idx]
        value = to_set[idx+1:]
        result = self.set_attr(obj, attr_name, value)
        if result.error:
            self.executor.msg(result.error)
        else:
            self.executor.msg("Set.")


class ScriptCommandMatcher(PythonCommandMatcher):
    priority = 10

    def access(self, interpreter: "Interpreter"):
        t = interpreter.entry.type
        if t == QueueEntryType.SCRIPT:
            return True
        elif t == QueueEntryType.IC:
            return interpreter.entry.session.build

    def at_cmdmatcher_creation(self):
        cmds = [DoListCommand, AssertCommand, BreakCommand, TriggerCommand, IncludeCommand, SwitchCommand,
                SetCommand]
        for cmd in cmds:
            self.add(cmd)
