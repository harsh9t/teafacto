import collections, inspect, argparse, dill as pkl, os, numpy as np, pandas as pd, sys
from datetime import datetime as dt


def loadlexidtsv(path, numwords=10, numchars=30):
    with open(path) as f:
        allgloveids = []    # 2D
        allcharmats = []    # 3D
        allfbids = []       # 1D

        c = 0
        for line in f:
            try:
                ns = line[:-1].split("\t")
                gloveids = map(int, ns[0].split(" "))
                charmat = []
                charsplits = ns[1].split(", ")
                charmat.extend([[int(y) if len(y) > 0 else 0 for y in x.split(" ")] for x in charsplits])
                fbid = int(ns[2])
                allgloveids.append(gloveids)
                allcharmats.append(charmat)
                allfbids.append(fbid)
                if c % 1e6 == 0:
                    print "%.0fM" % (c/1e6)
                c += 1
            except Exception, e:
                print line
                raise e
        allgloveids, allcharmats, allfbids = makenpfrom(allgloveids, allcharmats, allfbids, dtype="int32", numwords=numwords, numchars=numchars)
        return allgloveids, allcharmats, allfbids


def makenpfrom(tomat, toten, tovec, dtype="int32", numwords=15, numchars=30):
    i = 0
    delc = 0
    truncwc = 0
    assert(len(tomat) == len(toten) and len(toten) == len(tovec))
    while i < len(tomat):
        assert(len(tomat[i]) == len(toten[i]))
        if len(tomat[i]) > numwords:   # drop phrases longer than <numwords> words
            #print tovec[i]
            tomat[i] = tomat[i][:numwords]
            toten[i] = toten[i][:numwords]
            delc += 1
        else:
            tomat[i].extend([0]*(numwords - len(tomat[i])))
        j = 0
        while j < len(toten[i]):
            if len(toten[i][j]) > numchars:     # if word is too long, truncate
                toten[i][j] = toten[i][j][:numchars]
                truncwc += 1
            else:
                toten[i][j].extend([0]*(numchars-len(toten[i][j])))
            j += 1
        torep = [[0]*numchars]
        toten[i].extend(torep*(numwords-len(toten[i])))
        i += 1
        if i % 1e6 == 0:
            print "%.0fM, %d, %d" % ((i/1e6), delc, truncwc)
    print i, delc, truncwc
    return np.asarray(tomat, dtype=dtype), np.asarray(toten, dtype=dtype), np.asarray(tovec, dtype=dtype)


class ticktock(object):
    def __init__(self, prefix="-", verbose=True):
        self.prefix = prefix
        self.verbose = verbose
        self.state = None
        self.perc = None
        self.prevperc = None
        self._tick()

    def tick(self, state=None):
        if self.verbose and state is not None:
            print "%s: %s" % (self.prefix, state)
        self._tick()

    def _tick(self):
        self.ticktime = dt.now()

    def _tock(self):
        return (dt.now() - self.ticktime).total_seconds()

    def progress(self, x, of):
        if self.verbose:
            self.perc = int(round(100.* x/of))
            if self.perc != self.prevperc:
                print "%s: %d" % (self.prefix, self.perc)  + "%"
                self.prevperc = self.perc

    def tock(self, action=None, prefix=None):
        duration = self._tock()
        if self.verbose:
            prefix = prefix if prefix is not None else self.prefix
            action = action if action is not None else self.state
            print "%s: %s in %s" % (prefix, action, self._getdurationstr(duration))
        return self

    def msg(self, action=None, prefix=None):
        if self.verbose:
            prefix = prefix if prefix is not None else self.prefix
            action = action if action is not None else self.state
            print "%s: %s" % (prefix, action)
        return self

    def _getdurationstr(self, duration):
        if duration >= 60:
            duration = int(round(duration))
            seconds = duration % 60
            minutes = (duration // 60) % 60
            hours = (duration // 3600) % 24
            days = duration // (3600*24)
            acc = ""
            if seconds > 0:
                acc = ("%d second" % seconds) + ("s" if seconds > 1 else "")
            if minutes > 0:
                acc = ("%d minute" % minutes) + ("s" if minutes > 1 else "") + (", " + acc if len(acc) > 0 else "")
            if hours > 0:
                acc = ("%d hour" % hours) + ("s" if hours > 1 else "") + (", " + acc if len(acc) > 0 else "")
            if days > 0:
                acc = ("%d day" % days) + ("s" if days > 1 else "") + (", " + acc if len(acc) > 0 else "")
            return acc
        else:
            return ("%.3f second" % duration) + ("s" if duration > 1 else "")

    def live(self, x):
        if self.verbose:
            sys.stdout.write(self.prefix + ": " + x+("\t T: %s \r" % self._getdurationstr(self._tock())))
            sys.stdout.flush()

    def stoplive(self):
        if self.verbose:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()





def argparsify(f, test=None):
    args, _, _, defaults = inspect.getargspec(f)
    assert(len(args) == len(defaults))
    parser = argparse.ArgumentParser()
    i = 0
    for arg in args:
        parser.add_argument("-%s"%arg, "--%s"%arg, type=type(defaults[i]))
        i += 1
    if test is not None:
        par = parser.parse_args([test])
    else:
        par = parser.parse_args()
    kwargs = {}
    for arg in args:
        if getattr(par, arg) is not None:
            kwargs[arg] = getattr(par, arg)
    return kwargs


def argprun(f, **kwargs):   # command line overrides kwargs
    f_args = argparsify(f)
    for k, v in kwargs.items():
        if k not in f_args:
            f_args[k] = v
    f(**f_args)


def issequence(x):
    return isinstance(x, collections.Sequence) and not isinstance(x, basestring)


def isnumber(x):
    return isinstance(x, float) or isinstance(x, int)


def isstring(x):
    return isinstance(x, basestring)


def isfunction(x):
    return hasattr(x, "__call__")


class Saveable(object):
    def __init__(self, autosave=False, **kw):
        super(Saveable, self).__init__(**kw)
        self._autosave = autosave

    ############# Saving and Loading #################"
    def getdefaultsavepath(self):
        dir = "../../saves/"
        if not os.path.exists(os.path.join(os.path.dirname(__file__), dir)):
            os.makedirs(os.path.join(os.path.dirname(__file__), dir))
        dfile = os.path.join(os.path.dirname(__file__), dir+"%s.%s" %
                             (self.printname, dt.now().strftime("%Y-%m-%d=%H:%M")))
        return dfile

    @property
    def printname(self):
        return self.__class__.__name__

    def save(self, filepath=None):
        if filepath is None:
            filepath = self.getdefaultsavepath() + ".auto"
        with open(filepath, "w") as f:
            pkl.dump(self, f)
        return filepath

    # TODO: WILL FREEZE/UNFREEZE WORK WITH GPU?
    def freeze(self):
        return pkl.dumps(self)

    @staticmethod
    def unfreeze(dumps):
        return pkl.loads(dumps)

    @staticmethod
    def load(filepath):
        with open(filepath) as f:
            ret = pkl.load(f)
        return ret

    @property
    def autosave(self): # for saving after each iter
        self._autosave = True
        return self


if __name__ == "__main__":
    a, b, c = loadlexidtsv("../data/kgraph/labelsrevlex.map.id.tsv")
    print "loaded"
    pkl.dump((a, b, c), open("../My Passport/data/kgraph/labelsrevlex.map.id.tsv.pkl", "w"))
    print "dumped"
    a, b, c = loadlexidtsv("../My Passport/data/kgraph/aliasrevlex.map.id.tsv")
    pkl.dump((a, b, c), open("../My Passport/data/kgraph/aliasrevlex.map.id.tsv.pkl", "w"))