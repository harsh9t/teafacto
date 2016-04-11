import numpy as np, unidecode

from teafacto.core.datafeed import FeedTransform


class WordToWordCharTransform(FeedTransform):
    def __init__(self, worddic, unkwordid=1, numwords=10, numchars=30, **kw):
        super(WordToWordCharTransform, self).__init__(**kw)
        self.worddic = worddic
        self.unkwordid = unkwordid
        self.numwords = numwords
        self.numchars = numchars

    def getshapefor(self, datashape):
        return (datashape[0], self.numwords, self.numchars + 1)

    def transform(self, x):
        ret = np.zeros((x.shape[0], self.numwords, self.numchars + 1), dtype="int32")
        i = 0
        while i < x.shape[0]:
            j = 0
            while j < x.shape[1]:
                word = x[i, j]
                retword, skip = transinner((word, self.numchars, self.worddic, self.unkwordid))
                if max(retword[1:]) > 128:
                    print x
                if skip:
                    j = x.shape[1]
                else:
                    ret[i, j, :] = retword
                j += 1

            i += 1
        return ret


def transinner(args):
    #print " arg " + str(args[0])
    word = args[0]
    numchars = args[1]+1
    worddic = args[2]
    unkwordid = args[3]
    skip = False
    if word is None:
        retword = [0]*(numchars)         # missing word ==> all zeros
        skip = True
    else:
        word = unidecode.unidecode(word)
        if word in worddic:
            retword = [worddic[word]]      # get word index
        else:
            retword = [unkwordid]                       # unknown word
        retword.extend(map(ord, word))
        retword.extend([0]*(numchars-len(retword)))
    return retword, skip #np.asarray(retword, dtype="int32")