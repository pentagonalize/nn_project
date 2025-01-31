"""Some neural network layers that you can use in building your translation system.

Many of these layers are tailored for low-resource translation (thanks to Toan Nguyen)."""

import torch
import math

if torch.cuda.is_available():
    device = torch.device("cuda:0")
else:
    device = torch.device("cpu")

def bmv(w, x):
    """Matrix-vector multiplication that works even if x is a sequence of
    vectors.

    If w has size m,n and x has size n, performs a standard
    matrix-vector multiply, yielding a vector of size m.

    If w has size m,n and x has size b,n, multiplies w with every
    column of x, yielding a matrix of size b,m.
    """
    
    x = x.unsqueeze(-1)
    y = w @ x
    y = y.squeeze(-1)
    return y

class Embedding(torch.nn.Module):
    """Embedding layer.

    The constructor takes arguments:
        vocab_size: Vocabulary size (int)
        output_dims: Size of output vectors (int)

    The resulting Embedding object is callable. See the documentation
    for forward().
    """

    def __init__(self, vocab_size, output_dims):
        super().__init__()
        self.W = torch.nn.Parameter(torch.empty(vocab_size, output_dims))
        torch.nn.init.normal_(self.W, std=0.01)

    def forward(self, inp):
        """Works on either single words or sequences of words.

        Argument:
            inp: Word (int in {0,...,vocab_size-1})

        Return:
            Word embedding (tensor of size output_dims)

        *or*

        Argument:
            inp: Words (tensor of size n, elements are ints in {0,...,vocab_size-1})

        Return:
            Word embeddings (tensor of size n,output_dims)
        """

        if not (isinstance(inp, int) or inp.dtype in [torch.int32, torch.int64]):
            raise TypeError('input should be an integer or tensor of integers')
        
        emb = self.W[inp]
        
        # Scaling the embedding to have norm 1 helps against overfitting.
        # https://www.aclweb.org/anthology/N18-1031/
        emb = torch.nn.functional.normalize(emb, dim=-1)
        
        return emb

class RNN(torch.nn.Module):
    """Simple recurrent neural network.

    The constructor takes one argument:
        dims: Size of both the input and output vectors (int)

    The resulting RNN object can be used in two ways:
      - On a whole sequence at once, by calling the object (see documentation for forward())
      - Step by step, using start() and step(); please see the documentation for those methods.

    This implementation adds a _residual connection_, which just means
    that output vector is the standard output vector plus the input
    vector. This helps against overfitting, but makes the
    implementation slightly more complicated.
    """

    def __init__(self, dims):
        super().__init__()
        self.dims = dims
        self.h0 = torch.nn.Parameter(torch.empty(dims))
        self.W_hi = torch.nn.Parameter(torch.empty(dims, dims))
        self.W_hh = torch.nn.Parameter(torch.empty(dims, dims))
        self.b = torch.nn.Parameter(torch.empty(dims))
        torch.nn.init.normal_(self.h0, std=0.01)
        torch.nn.init.normal_(self.W_hi, std=0.01)
        torch.nn.init.normal_(self.W_hh, std=0.01)
        torch.nn.init.normal_(self.b, std=0.01)

    def start(self):
        """Return the initial state."""
        return self.h0

    def step(self, state, inp):
        """Given the old state, read in an input vector (inp) and
        compute the new state and output vector (out).

        Arguments:
            state:  State (Tensor of size dims)
            inp:    Input vector (Tensor of size dims)

        Returns: (state, out), where
            state:  State (Tensor of size dims)
            out:    Output vector (Tensor of size dims)
        """

        if state.size()[-1] != self.dims:
            raise TypeError(f'Previous hidden-state vector must have size {self.dims}')
        if inp.size()[-1] != self.dims:
            raise TypeError(f'Input vector must have size {self.dims}')

        state = torch.tanh(bmv(self.W_hi, inp) + bmv(self.W_hh, state) + self.b)
        return (state, state + inp)

    def forward(self, inputs):
        """Run the RNN on an input sequence.
        Argument:
            Input vectors (Tensor of size n,dims)

        Return:
            Output vectors (Tensor of size n,dims)
        """

        if inputs.ndim != 2:
            raise TypeError("inputs must have exactly two axes")
        if inputs.size()[1] != self.dims:
            raise TypeError(f'Input vectors must have size {self.dims}')

        h = self.start()
        outputs = []
        for inp in inputs:
            h, o = self.step(h, inp)
            outputs.append(o)
        return torch.stack(outputs)

class LinearLayer(torch.nn.Module):
    """Linear layer.

    The constructor takes these arguments:
        input_dims:  Size of input vectors (int)
        output_dims: Size of output vectors (int)
        residual:    Add a residual connection (bool)

    The resulting LinearLayer object is callable. See forward().

    If residual is True, then input_dims and output_dims must be equal.
    """
    def __init__(self, input_dims, output_dims, residual=False):
        super().__init__()
        self.residual = residual
        if residual and input_dims != output_dims:
            raise ValueError("A residual connection requires the same number of input and output dimensions.")
        self.W = torch.nn.Parameter(torch.empty(output_dims, input_dims))
        self.b = torch.nn.Parameter(torch.empty(output_dims))
        torch.nn.init.normal_(self.W, std=0.01)
        torch.nn.init.normal_(self.b, std=0.01)

    def forward(self, inp):
        """Works on either single vectors or sequences of vectors.

        Argument:
            inp: Input vector (tensor of size input_dims)

        Return:
            Output vector (tensor of size output_dims)

        *or*

        Argument:
            inp: Input vectors (tensor of size n,input_dims)

        Return:
            Output vectors (tensor of size n,output_dims)
        """
        
        input_dims = self.W.size()[-1]
        if inp.size()[-1] != input_dims:
            raise TypeError(f"The inputs must have size {input_dims} (not {inp.size()[-1]})")
        
        out = bmv(self.W, inp) + self.b
        if self.residual:
            out = out + inp
        return out
        
class SoftmaxLayer(torch.nn.Module):
    """Softmax layer.

    The constructor takes these arguments:
        input_dims:  Size of input vectors (int)
        output_dims: Size of output vectors (int)

    The resulting SoftmaxLayer is callable (see forward()).
    """
    def __init__(self, input_dims, output_dims):
        super().__init__()
        self.W = torch.nn.Parameter(torch.empty(output_dims, input_dims))
        torch.nn.init.normal_(self.W, std=0.01)

    def forward(self, inp):
        """Works on either single vectors or sequences of vectors.

        Argument:
            inp: Input vector (tensor of size input_dims)

        Return:
            Vector of log-probabilities (tensor of size output_dims)

        *or*

        Argument:
            inp: Input vectors (tensor of size n,input_dims)

        Return:
            Vectors of log-probabilities (tensor of size n,output_dims)
        """

        input_dims = self.W.size()[-1]
        if inp.size()[-1] != input_dims:
            raise TypeError(f"The inputs must have size {input_dims}")
        
        # Scaling both the output embeddings and the inputs
        # to have norm 1 and 10, respectively, helps against overfitting.
        # https://www.aclweb.org/anthology/N18-1031/
        W = torch.nn.functional.normalize(self.W, dim=1)
        inp = torch.nn.functional.normalize(inp, dim=-1) * 10

        return torch.log_softmax(bmv(W, inp), dim=-1)

def attention(query, keys, vals, mask=None, temp=1):
    """Compute dot-product attention.

    query can be a single vector or a sequence of vectors.

    Arguments:
        keys:  Key vectors (tensor with size n,d)
        query: Query vector (tensor with size d)
        vals:  Value vectors (tensor with size n,d')
        mask:  Mask (tensor with size n and dtype bool)

    Returns:
        Context vector (tensor with size d')

    *or*

    Arguments:
        keys:  Key vectors (tensor with size n,d)
        query: Query vectors (tensor with size m,d)
        vals:  Value vectors (tensor with size n,d')
        mask:  Mask (tensor with size m,n and dtype bool)

    Returns:
        Context vectors (tensor with size m,d')
    """
    
    if query.size()[-1] != keys.size()[-1]:
        raise TypeError("The queries and keys should be the same size")
    d = query.size()[-1]
    if keys.size()[-2] != vals.size()[-2]:
        raise TypeError("There must be the same number of keys and values")
    if mask is not None:
        if len(query.size()) >= 2 and mask.size()[-2] != query.size()[-2]:
            raise TypeError("Mask has wrong size")
        if mask.size()[-1] != keys.size()[-2]:
            raise TypeError("Mask has wrong size")

    logits = query @ keys.transpose(-2, -1) / math.sqrt(d) # m,n
    if mask is not None:
        logits.masked_fill_(mask, -torch.inf)
    aweights = torch.softmax(logits / temp, dim=-1)        # m,n
    context = aweights @ vals                              # m,d'
    return context


def hardAttention(query, keys, vals, mask=None, gumbel=True):
    """Compute hard dot-product attention.

    query can be a single vector or a sequence of vectors.

    Arguments:
        keys:  Key vectors (tensor with size n,d)
        query: Query vector (tensor with size d)
        vals:  Value vectors (tensor with size n,d')
        mask:  Mask (tensor with size n and dtype bool)

    Returns:
        Context vector (tensor with size d')

    *or*

    Arguments:
        keys:  Key vectors (tensor with size n,d)
        query: Query vectors (tensor with size m,d)
        vals:  Value vectors (tensor with size n,d')
        mask:  Mask (tensor with size m,n and dtype bool)

    Returns:
        Context vectors (tensor with size m,d')
    """

    if query.size()[-1] != keys.size()[-1]:
        raise TypeError("The queries and keys should be the same size")
    d = query.size()[-1]
    if keys.size()[-2] != vals.size()[-2]:
        raise TypeError("There must be the same number of keys and values")
    if mask is not None:
        if len(query.size()) >= 2 and mask.size()[-2] != query.size()[-2]:
            raise TypeError("Mask has wrong size")
        if mask.size()[-1] != keys.size()[-2]:
            raise TypeError("Mask has wrong size")

    logits = query @ keys.transpose(-2, -1) / math.sqrt(d)                             # m,n
    if mask is not None:
        logits.masked_fill_(mask, -torch.inf)
    aweights = torch.softmax(logits, dim=-1)                                           # m,n
    if gumbel:
        # Gumbel softmax
        choices = torch.nn.functional.gumbel_softmax(aweights, dim=1, hard=True, tau=0.1) # m
    else:
        # Argmax
        choices = torch.argmax(aweights, dim=1).float()
    context = choices @ vals                                                           # m,d'
    return context

class AttentionLayer(torch.nn.Module):
    """Base class for attention layers."""

    def __init__(self, dims):
        super().__init__()
        self.dims = dims
        self.W_Q = torch.nn.Parameter(torch.empty(dims, dims))
        self.W_K = torch.nn.Parameter(torch.empty(dims, dims))
        self.W_V = torch.nn.Parameter(torch.empty(dims, dims))
        torch.nn.init.normal_(self.W_Q, std=0.01)
        torch.nn.init.normal_(self.W_K, std=0.01)
        torch.nn.init.normal_(self.W_V, std=0.01)

class SelfAttentionLayer(AttentionLayer):
    """Self-attention layer, for use in an encoder.

    The constructor takes one argument:
        dims: Size of input and output vectors (int)

    The resulting object is callable (see forward()) but can only be
    used on sequences of vectors, not single vectors.
    """
    
    def forward(self, inputs):
        """Argument:
            inputs: Input vectors (tensor of size n,d)

        Return:
            Output vectors (tensor of size n,d)
        """

        if inputs.ndim < 2:
            raise TypeError("inputs must have at least two axes")
        if inputs.size()[-1] != self.dims:
            raise TypeError(f"input vectors must have size {self.dims}")

        # Linearly transform inputs in three ways to get queries, keys, values
        queries = bmv(self.W_Q, inputs)
        keys = bmv(self.W_K, inputs)
        values = bmv(self.W_V, inputs)

        # Compute output vectors
        outputs = attention(queries, keys, values)
        
        # Residual connection (see RNN for explanation)
        outputs = outputs + inputs
        
        return outputs

class HardSelfAttentionLayer(AttentionLayer):
    """Hard Self-attention layer, for use in an encoder.

    The constructor takes one argument:
        dims: Size of input and output vectors (int)

    The resulting object is callable (see forward()) but can only be
    used on sequences of vectors, not single vectors.
    """

    def forward(self, inputs, gumbel=True):
        """Argument:
            inputs: Input vectors (tensor of size n,d)
            gumbel: Whether to use Gumbel softmax or argmax

        Return:
            Output vectors (tensor of size n,d)
        """

        if inputs.ndim < 2:
            raise TypeError("inputs must have at least two axes")
        if inputs.size()[-1] != self.dims:
            raise TypeError(f"input vectors must have size {self.dims}")

        # Linearly transform inputs in three ways to get queries, keys, values
        queries = bmv(self.W_Q, inputs)
        keys = bmv(self.W_K, inputs)
        values = bmv(self.W_V, inputs)

        # Compute output vectors
        if gumbel:
            outputs = hardAttention(queries, keys, values)
        else:
            outputs = hardAttention(queries, keys, values, gumbel=False)
        # Residual connection (see RNN for explanation)
        outputs = outputs + inputs

        return outputs

class MaskedSelfAttentionLayer(AttentionLayer):
    """Masked self-attention layer, for use in a decoder.

    The constructor takes one argument:
        dims: Size of input and output vectors (int)

    The resulting object is callable (see forward()) but can only be
    used on sequences of vectors, not single vectors. It also has
    start() and step() methods; please see documentation for those
    methods.
    """
    
    def start(self):
        """The state is the list of previous inputs, which is initially empty."""
        return torch.empty(0, self.dims)

    def step(self, prev_inps, inp):
        """Input a new vector and compute masked self-attention over all input vectors."""
        inputs = torch.cat([prev_inps, inp.unsqueeze(0)], dim=0)

        # Linearly transform inputs in three ways to get queries, keys, values
        query = bmv(self.W_Q, inp)
        keys = bmv(self.W_K, inputs)
        values = bmv(self.W_V, inputs)

        # Compute output vectors
        output = attention(query, keys, values)
        
        # Residual connection
        output = output + inp
        
        return (inputs, output)
    
    def forward(self, inputs, ):
        """Argument:
            inputs: Input vectors (tensor of size n,d)

        Return:
            Output vectors (tensor of size n,d)
        """

        if inputs.ndim < 2:
            raise TypeError("inputs must have at least two axes")
        n = inputs.size()[-2]
        if inputs.size()[-1] != self.dims:
            raise TypeError(f"input vectors must have size {self.dims}")

        # Linearly transform inputs in three ways to get queries, keys, values
        queries = bmv(self.W_Q, inputs)
        keys = bmv(self.W_K, inputs)
        values = bmv(self.W_V, inputs)

        # Compute output vectors
        mask = torch.arange(n).unsqueeze(1) < torch.arange(n)
        mask = mask.to(device)
        outputs = attention(queries, keys, values, mask=mask)
        del mask
        
        # Residual connection (see RNN for explanation)
        outputs = outputs + inputs
        
        return outputs

class MaskedSelfAttentionLayerTemp(AttentionLayer):
    """Masked self-attention layer, for use in a decoder.

    The constructor takes one argument:
        dims: Size of input and output vectors (int)

    The resulting object is callable (see forward()) but can only be
    used on sequences of vectors, not single vectors. It also has
    start() and step() methods; please see documentation for those
    methods.
    """

    def start(self):
        """The state is the list of previous inputs, which is initially empty."""
        return torch.empty(0, self.dims)

    def step(self, prev_inps, inp):
        """Input a new vector and compute masked self-attention over all input vectors."""
        inputs = torch.cat([prev_inps, inp.unsqueeze(0)], dim=0)

        # Linearly transform inputs in three ways to get queries, keys, values
        query = bmv(self.W_Q, inp)
        keys = bmv(self.W_K, inputs)
        values = bmv(self.W_V, inputs)

        # Compute output vectors
        output = attention(query, keys, values)

        # Residual connection
        output = output + inp

        return (inputs, output)

    def forward(self, inputs, ):
        """Argument:
            inputs: Input vectors (tensor of size n,d)

        Return:
            Output vectors (tensor of size n,d)
        """

        if inputs.ndim < 2:
            raise TypeError("inputs must have at least two axes")
        n = inputs.size()[-2]
        if inputs.size()[-1] != self.dims:
            raise TypeError(f"input vectors must have size {self.dims}")

        # Linearly transform inputs in three ways to get queries, keys, values
        queries = bmv(self.W_Q, inputs)
        keys = bmv(self.W_K, inputs)
        values = bmv(self.W_V, inputs)

        # get 1/n^3 temperature
        temp = 1/(n**3)

        # Compute output vectors
        mask = torch.arange(n).unsqueeze(1) < torch.arange(n)
        mask = mask.to(device)
        outputs = attention(queries, keys, values, mask=mask, temp=temp)
        del mask

        # Residual connection (see RNN for explanation)
        outputs = outputs + inputs

        return outputs

class CrossAttentionLayer(AttentionLayer):
    """Cross-attention layer, for use in a decoder.

    The constructor takes one argument:
        dims: Size of input and output vectors (int)

    The resulting object is callable (see forward()).
    """
    
    def forward(self, finputs, einputs):
        """Arguments:
            finputs: Source-side input vectors (tensor of size n,d)
            einputs: Target-side input vector or vectors (tensor of size d or m,d)

        Return:
            Output vectors (tensor of size d or m,d)
        """

        if finputs.ndim < 2:
            raise TypeError("finputs must have at least two axes")
        if finputs.size()[-1] != self.dims:
            raise TypeError(f"finputs vectors must have size {self.dims}")
        if einputs.size()[-1] != self.dims:
            raise TypeError(f"einputs vectors must have size {self.dims}")

        # Linearly transform inputs in three ways to get queries, keys, values
        queries = bmv(self.W_Q, einputs)
        keys = bmv(self.W_K, finputs)
        values = bmv(self.W_V, finputs)

        # Compute output vectors
        outputs = attention(queries, keys, values)
        
        # Residual connection (see RNN for explanation)
        outputs = outputs + einputs
        
        return outputs
    
class MHSelfAttentionLayer(torch.nn.Module):
    """Multi-head self-attention layer."""
    def __init__(self, nheads, dims):
        super().__init__()
        self.heads = torch.nn.ModuleList([SelfAttentionLayer(dims) for h in range(nheads)])

    def forward(self, inp):
        return sum([h(inp) for h in self.heads]) / len(self.heads)

class FFN(torch.nn.Module):
    def __init__(self, idims, hdims, odims, residual=True):
        super().__init__()
        self.lin1 = LinearLayer(idims, hdims)
        self.lin2 = LinearLayer(hdims, odims)
        self.residual = residual

    def forward(self, inp):
        hid = torch.relu(self.lin1(inp))
        out = self.lin2(hid)
        if self.residual:
            return inp + out
        else:
            return out
